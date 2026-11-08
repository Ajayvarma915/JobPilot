from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
from typing import Any
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from app.collectors.base import JobCollector


class WorkdayCollector(JobCollector):
    """Collect public Workday CXS job postings for one verified tenant/site.

    The tenant, Workday cluster host (for example wd5), and site name must be
    confirmed from the employer's official apply URL. Do not guess these values.
    """

    def __init__(
        self,
        tenant: str,
        site: str,
        company_name: str,
        *,
        host: str,
        locale: str = "en-US",
        website: str | None = None,
        careers_url: str | None = None,
        page_size: int = 20,
        max_pages: int = 25,
        fetch_details: bool = True,
        timeout: int = 30,
    ) -> None:
        self.tenant = tenant.strip()
        self.site = site.strip()
        self.company_name = company_name.strip()
        self.host = host.strip().rstrip("/")
        if self.host and not self.host.startswith("https://"):
            self.host = "https://" + self.host
        if not all((self.tenant, self.site, self.company_name, self.host)):
            raise ValueError("Workday tenant, site, company_name and host are required.")
        if page_size < 1 or page_size > 100 or max_pages < 1:
            raise ValueError("Invalid Workday pagination settings.")
        self.locale = locale
        self.website = website
        self.careers_url = careers_url
        self.page_size = page_size
        self.max_pages = max_pages
        self.fetch_details = fetch_details
        self.timeout = timeout
        self.source = f"workday:{self.tenant.casefold()}:{self.site.casefold()}"
        self.api_root = f"{self.host}/wday/cxs/{quote(self.tenant, safe='')}/{quote(self.site, safe='')}"
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "JobPilot/1.0 (personal job discovery)",
            "X-CALYPSO-CSRF-TOKEN": "", 
        })

    def collect(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        offset = 0
        for _ in range(self.max_pages):
            response = self.session.post(
                f"{self.api_root}/jobs",
                json={"appliedFacets": {}, "limit": self.page_size, "offset": offset, "searchText": ""},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError(f"Unexpected Workday response for '{self.company_name}'.")
            postings = payload.get("jobPostings") or []
            if not isinstance(postings, list):
                raise ValueError("Workday response 'jobPostings' must be a list.")
            for raw in postings:
                if not isinstance(raw, dict):
                    continue
                job = self._normalise_summary(raw)
                if job is None or job["external_id"] in seen:
                    continue
                seen.add(job["external_id"])
                if self.fetch_details:
                    detail = self._fetch_detail(str(raw.get("externalPath") or ""))
                    if detail:
                        job.update(detail)
                    else:
                        job["_jobpilot_detail_fetch_status"] = "failed"
                results.append(job)
            total = payload.get("total")
            offset += len(postings)
            if not postings or len(postings) < self.page_size:
                break
            if isinstance(total, int) and offset >= total:
                break
        return results

    def _normalise_summary(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        title = str(raw.get("title") or "").strip()
        external_path = str(raw.get("externalPath") or "").strip()
        if not title or not external_path:
            return None
        req_id = str(raw.get("jobReqId") or raw.get("id") or external_path).strip()
        location = str(raw.get("locationsText") or raw.get("location") or "").strip()
        posted = raw.get("postedOn")
        public_path = f"/{self.locale}/{quote(self.site, safe='')}/{external_path.lstrip('/')}"
        job_url = urljoin(self.host + "/", public_path.lstrip("/"))
        return {
            "external_id": req_id,
            "company": self.company_name,
            "title": title,
            "location": [location] if location else [],
            "url": job_url,
            "description": "",
            "experience_level": None,
            "employment_type": None,
            "posted_at": self._parse_date(posted),
            "source": self.source,
            "external_path": external_path,
            "department": raw.get("jobFamilyGroup") or raw.get("jobFamily"),
            "workplace_type": raw.get("workplaceType"),
            "_jobpilot_detail_fetch_status": "pending" if self.fetch_details else "not_requested",
        }

    def _fetch_detail(self, external_path: str) -> dict[str, Any] | None:
        if not external_path:
            return None
        # Workday CXS detail uses the site root followed directly by externalPath.
        # Adding another /job segment causes requests to /job/job/... and loses details.
        detail_url = f"{self.api_root}{external_path if external_path.startswith('/') else '/' + external_path}"
        try:
            response = self.session.get(detail_url, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        info = payload.get("jobPostingInfo")
        if not isinstance(info, dict):
            return None
        description_html = str(info.get("jobDescription") or info.get("externalDescription") or "")
        description = self._html_to_text(description_html)
        title = str(info.get("jobTitle") or info.get("title") or "").strip()
        locations: list[str] = []
        for key in ("location", "additionalLocations", "jobRequisitionLocation"):
            for value in self._location_values(info.get(key)):
                if value.casefold() not in {item.casefold() for item in locations}:
                    locations.append(value)
        detail = {
            "description": description,
            "employment_type": info.get("timeType") or info.get("workerSubType"),
            "posted_at": self._parse_date(info.get("postedOn")),
            "department": info.get("jobFamilyGroup") or info.get("jobFamily"),
            "workplace_type": info.get("workplaceType"),
            "_jobpilot_detail_fetch_status": "fetched" if description else "fetched_without_description",
            **({"title": title} if title else {}),
        }
        if locations:
            detail["location"] = locations
        external_url = str(info.get("externalUrl") or "").strip()
        if external_url:
            detail["url"] = urljoin(self.host + "/", external_url)
        return detail

    @classmethod
    def _location_values(cls, value: Any) -> list[str]:
        """Normalize Workday string/list/dict location variants."""
        if value is None:
            return []
        if isinstance(value, str):
            clean = " ".join(value.split())
            return [clean] if clean else []
        if isinstance(value, (list, tuple)):
            output: list[str] = []
            for item in value:
                for location in cls._location_values(item):
                    if location.casefold() not in {entry.casefold() for entry in output}:
                        output.append(location)
            return output
        if isinstance(value, dict):
            for key in ("descriptor", "fullLocation", "displayName", "name", "location"):
                if value.get(key):
                    return cls._location_values(value[key])
            parts = [str(value.get(key) or "").strip() for key in ("city", "region", "country")]
            combined = ", ".join(part for part in parts if part)
            return [combined] if combined else []
        return []

    @staticmethod
    def _parse_date(value: Any) -> Any:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        text = str(value).strip()
        for fmt in ("%b %d, %Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%fZ"):
            try:
                parsed = datetime.strptime(text, fmt)
                return parsed.replace(tzinfo=timezone.utc).replace(tzinfo=None)
            except ValueError:
                continue
        return None

    @staticmethod
    def _html_to_text(value: str) -> str:
        soup = BeautifulSoup(unescape(value), "html.parser")
        for node in soup(["script", "style"]):
            node.decompose()
        return "\n".join(
            " ".join(line.split())
            for line in soup.get_text("\n").splitlines()
            if line.strip()
        )
