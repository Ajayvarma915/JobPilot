from __future__ import annotations

from datetime import datetime
from html import unescape
from typing import Any
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from app.collectors.base import JobCollector


class OracleHCMCollector(JobCollector):
    """Collect public Candidate Experience requisitions from Oracle Recruiting Cloud.

    This is the public careers-site feed, not the authenticated recruiter REST API.
    The tenant host and site identifier must be copied from the employer's official
    CandidateExperience URL. The endpoint/response shape can vary by Oracle pod,
    so a first dry-run is required before marking an employer mapping as verified.
    """

    def __init__(
        self,
        base_url: str,
        site_number: str,
        company_name: str,
        *,
        language: str = "en",
        country_code: str = "IN",
        page_size: int = 100,
        max_pages: int = 20,
        timeout: int = 30,
    ) -> None:
        self.base_url = base_url.strip().rstrip("/")
        self.site_number = site_number.strip()
        self.company_name = company_name.strip()
        if not all((self.base_url, self.site_number, self.company_name)):
            raise ValueError("Oracle HCM base_url, site_number and company_name are required.")
        if page_size < 1 or page_size > 100 or max_pages < 1:
            raise ValueError("Invalid Oracle HCM pagination settings.")
        self.language = language
        self.country_code = country_code
        self.page_size = page_size
        self.max_pages = max_pages
        self.timeout = timeout
        self.source = f"oracle_hcm:{self.site_number.casefold()}"
        self.api_url = f"{self.base_url}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "JobPilot/1.0 (personal job discovery; public career postings)",
            "Referer": f"{self.base_url}/hcmUI/CandidateExperience/{self.language}/sites/{quote(self.site_number, safe='')}/jobs",
        })

    def collect(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        offset = 0
        for _ in range(self.max_pages):
            finder = (
                f"findReqs;siteNumber={self.site_number},offset={offset},"
                f"limit={self.page_size},workLocationCountryCode={self.country_code}"
            )
            response = self.session.get(
                self.api_url,
                params={"onlyData": "true", "expand": "requisitionList", "finder": finder},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            rows = self._extract_requisitions(payload)
            if not rows:
                break
            for raw in rows:
                job = self._normalize(raw)
                if job is None or job["external_id"] in seen:
                    continue
                seen.add(job["external_id"])
                results.append(job)
            if len(rows) < self.page_size:
                break
            offset += len(rows)
        return results

    @staticmethod
    def _extract_requisitions(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if not isinstance(payload, dict):
            raise ValueError("Unexpected Oracle HCM response type.")
        items = payload.get("items")
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                nested = item.get("requisitionList")
                if isinstance(nested, list):
                    return [row for row in nested if isinstance(row, dict)]
                # Some candidate-experience pods return requisitions directly.
                if any(key in item for key in ("Title", "JobTitle", "RequisitionTitle")):
                    return [row for row in items if isinstance(row, dict)]
        nested = payload.get("requisitionList")
        if isinstance(nested, list):
            return [row for row in nested if isinstance(row, dict)]
        return []

    def _normalize(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        external_id = str(
            raw.get("Id") or raw.get("RequisitionId") or raw.get("RequisitionNumber")
            or raw.get("JobRequisitionId") or raw.get("Number") or ""
        ).strip()
        title = str(raw.get("Title") or raw.get("JobTitle") or raw.get("RequisitionTitle") or "").strip()
        if not external_id or not title:
            return None

        path = str(raw.get("ExternalUrlSeo") or raw.get("ExternalUrl") or raw.get("ExternalApplicationUrl") or "").strip()
        if path.startswith("http://") or path.startswith("https://"):
            url = path
        elif path:
            url = urljoin(self.base_url, path)
        else:
            url = f"{self.base_url}/hcmUI/CandidateExperience/{self.language}/sites/{quote(self.site_number, safe='')}/jobs/{quote(external_id, safe='') }"

        location = raw.get("PrimaryLocation") or raw.get("PrimaryLocationName") or raw.get("LocationName") or raw.get("WorkLocation") or ""
        if isinstance(location, dict):
            location = ", ".join(str(location.get(key) or "").strip() for key in ("City", "Region", "Country") if location.get(key))
        locations = [str(location).strip()] if str(location).strip() else []

        description_parts = []
        for key in ("ExternalDescription", "ShortDescriptionStr", "JobDescription", "Description", "ExternalDescriptionHtml"):
            value = raw.get(key)
            if value:
                description_parts.append(self._html_to_text(str(value)))
        description = "\n".join(dict.fromkeys(part for part in description_parts if part))

        return {
            "external_id": external_id,
            "company": self.company_name,
            "title": title,
            "location": locations,
            "url": url,
            "description": description,
            "experience_level": None,
            "employment_type": raw.get("RegularOrTemporary") or raw.get("WorkerType") or raw.get("EmploymentType"),
            "posted_at": self._parse_date(raw.get("PostedDate") or raw.get("ExternalPostedDate") or raw.get("PostingStartDate")),
            "source": self.source,
            "department": raw.get("OrganizationName") or raw.get("DepartmentName"),
            "workplace_type": raw.get("WorkplaceType"),
        }

    @staticmethod
    def _parse_date(value: Any) -> datetime | None:
        if not value:
            return None
        text = str(value).strip()
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%b %d, %Y"):
            try:
                parsed = datetime.strptime(text, fmt)
                return parsed.replace(tzinfo=None)
            except ValueError:
                continue
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            return None

    @staticmethod
    def _html_to_text(value: str) -> str:
        soup = BeautifulSoup(unescape(value), "html.parser")
        for node in soup(["script", "style"]):
            node.decompose()
        return "\n".join(" ".join(line.split()) for line in soup.get_text("\n").splitlines() if line.strip())
