from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.collectors.base import JobCollector


class AmazonJobsCollector(JobCollector):
    """Collect India software-development roles from Amazon's public career search.

    Amazon exposes its own public search JSON route rather than one of the common
    ATS board APIs. The route and query fields mirror the public Amazon.jobs search
    page. Search is restricted to India + Software Development; descriptions are
    fetched for role/experience validation. No login or account automation is used.
    """

    SEARCH_URL = "https://www.amazon.jobs/en/search.json"
    BASE_URL = "https://www.amazon.jobs"

    def __init__(
        self,
        company_name: str = "Amazon",
        *,
        max_pages_per_band: int = 4,
        page_size: int = 100,
        experience_bands: tuple[str, ...] = ("less_than_one_year", "one_to_three_years"),
        fetch_details: bool = True,
        max_detail_fetch: int = 200,
        timeout: int = 30,
    ) -> None:
        if max_pages_per_band < 1 or page_size < 1 or page_size > 100:
            raise ValueError("Invalid Amazon jobs pagination settings.")
        self.company_name = company_name
        self.max_pages_per_band = max_pages_per_band
        self.page_size = page_size
        self.experience_bands = experience_bands
        self.fetch_details = fetch_details
        self.max_detail_fetch = max_detail_fetch
        self.timeout = timeout
        self.source = "amazon_jobs:india_software_development"
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json,text/html,*/*",
            "User-Agent": "JobPilot/1.0 (personal job discovery; public career search)",
        })

    def collect(self) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        seen: set[str] = set()
        detail_fetches_attempted = 0
        for band in self.experience_bands:
            offset = 0
            for _ in range(self.max_pages_per_band):
                response = self.session.get(
                    self.SEARCH_URL,
                    params={
                        "category[]": "software-development",
                        "country[]": "IND",
                        "industry_experience": band,
                        "offset": offset,
                        "result_limit": self.page_size,
                        "sort": "recent",
                    },
                    timeout=self.timeout,
                )
                response.raise_for_status()
                payload = response.json()
                page_jobs = self._extract_jobs(payload)
                if not page_jobs:
                    break
                for raw in page_jobs:
                    normalized = self._normalize(raw)
                    if normalized is None:
                        continue
                    key = normalized["external_id"]
                    if key in seen:
                        continue
                    seen.add(key)
                    jobs.append(normalized)

                    # Amazon's search JSON normally already contains the full
                    # description and qualifications. Do not issue a second
                    # page request when that content is already present.
                    description = str(normalized.get("description") or "").strip()
                    needs_detail = not description
                    if (
                        self.fetch_details
                        and needs_detail
                        and detail_fetches_attempted < self.max_detail_fetch
                    ):
                        detail_fetches_attempted += 1
                        detail = self._fetch_detail(normalized["url"])
                        if detail:
                            normalized.update(detail)
                if len(page_jobs) < self.page_size:
                    break
                offset += self.page_size
        return jobs

    @staticmethod
    def _extract_jobs(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            raise ValueError("Unexpected Amazon jobs search response.")
        for key in ("jobs", "search_results", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        # Some versions wrap the result array in a response object.
        for value in payload.values():
            if isinstance(value, dict):
                for key in ("jobs", "search_results", "results"):
                    nested = value.get(key)
                    if isinstance(nested, list):
                        return [item for item in nested if isinstance(item, dict)]
        return []

    def _normalize(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        external_id = str(raw.get("id") or raw.get("job_id") or raw.get("jobId") or "").strip()
        title = str(raw.get("title") or raw.get("job_title") or "").strip()
        if not external_id or not title:
            return None
        path = str(raw.get("job_path") or raw.get("jobPath") or raw.get("url") or "").strip()
        if path and path.startswith("http"):
            url = path
        elif path:
            url = urljoin(self.BASE_URL, path)
        else:
            url = f"{self.BASE_URL}/en/jobs/{external_id}"

        location = raw.get("location") or raw.get("normalized_location") or raw.get("locations") or ""
        if isinstance(location, dict):
            location = location.get("display_name") or location.get("name") or location.get("location") or ""
        if isinstance(location, list):
            locations = [str(item.get("display_name") or item.get("name") or item).strip() for item in location]
        else:
            locations = [str(location).strip()] if str(location).strip() else []

        description = "\n".join(
            str(raw.get(key) or "").strip()
            for key in ("description", "basic_qualifications", "preferred_qualifications")
            if raw.get(key)
        )
        posted = str(raw.get("posted_date") or raw.get("postedDate") or "").strip() or None
        return {
            "external_id": external_id,
            "company": self.company_name,
            "title": title,
            "location": list(dict.fromkeys(locations)),
            "url": url,
            "description": self._html_to_text(description) if "<" in description else description,
            "experience_level": raw.get("industry_experience") or raw.get("experience_level"),
            "employment_type": raw.get("job_type") or raw.get("employment_type"),
            "posted_at": self._parse_date(posted),
            "source": self.source,
            "department": raw.get("team") or raw.get("category"),
        }

    def _fetch_detail(self, url: str) -> dict[str, Any] | None:
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException:
            return None
        soup = BeautifulSoup(response.text, "html.parser")
        details: dict[str, Any] = {}
        for node in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                payload = json.loads(node.string or node.get_text())
            except (ValueError, TypeError):
                continue
            candidates = payload if isinstance(payload, list) else [payload]
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                if item.get("@type") == "JobPosting":
                    description = str(item.get("description") or "")
                    location = item.get("jobLocation")
                    if description:
                        details["description"] = self._html_to_text(description)
                    if location and not details.get("location"):
                        details["location"] = self._jsonld_locations(location)
                    if item.get("datePosted"):
                        details["posted_at"] = self._parse_date(str(item["datePosted"]))
                    return details
        # Fallback for the server-rendered job description block.
        for selector in (".job-description", "#job-description", "[data-test='job-description']"):
            node = soup.select_one(selector)
            if node:
                details["description"] = self._html_to_text(str(node))
                break
        return details or None

    @staticmethod
    def _jsonld_locations(value: Any) -> list[str]:
        values = value if isinstance(value, list) else [value]
        results: list[str] = []
        for item in values:
            if not isinstance(item, dict):
                continue
            address = item.get("address") or {}
            if isinstance(address, dict):
                label = ", ".join(str(address.get(k) or "").strip() for k in ("addressLocality", "addressRegion", "addressCountry") if address.get(k))
                if label:
                    results.append(label)
        return results

    @staticmethod
    def _parse_date(value: str | None) -> Any:
        if not value:
            return None
        text = value.strip()
        for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
            try:
                from datetime import datetime
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        try:
            from datetime import datetime
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
