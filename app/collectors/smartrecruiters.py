from __future__ import annotations

from datetime import datetime
from html import unescape
from typing import Any
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from app.collectors.base import JobCollector


class SmartRecruitersCollector(JobCollector):
    """Collect public postings from the SmartRecruiters Posting API."""

    API_ROOT = "https://api.smartrecruiters.com/v1/companies"

    def __init__(
        self,
        company_identifier: str,
        company_name: str,
        *,
        website: str | None = None,
        careers_url: str | None = None,
        page_size: int = 100,
        max_pages: int = 20,
        timeout: int = 30,
    ) -> None:
        self.company_identifier = company_identifier.strip()
        self.company_name = company_name.strip()
        if not self.company_identifier or not self.company_name:
            raise ValueError("SmartRecruiters company_identifier and company_name are required.")
        if page_size < 1 or page_size > 100:
            raise ValueError("SmartRecruiters page_size must be between 1 and 100.")
        if max_pages < 1:
            raise ValueError("SmartRecruiters max_pages must be positive.")
        self.website = website
        self.careers_url = careers_url
        self.page_size = page_size
        self.max_pages = max_pages
        self.timeout = timeout
        self.source = f"smartrecruiters:{self.company_identifier.casefold()}"
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "JobPilot/1.0 (personal job discovery)",
        })

    def collect(self) -> list[dict[str, Any]]:
        base = f"{self.API_ROOT}/{quote(self.company_identifier, safe='')}/postings"
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        offset = 0
        for _ in range(self.max_pages):
            response = self.session.get(
                base,
                params={"limit": self.page_size, "offset": offset, "country": "in"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError(f"Unexpected SmartRecruiters response for '{self.company_identifier}'.")
            content = payload.get("content") or []
            if not isinstance(content, list):
                raise ValueError("SmartRecruiters response 'content' must be a list.")
            for raw in content:
                if not isinstance(raw, dict):
                    continue
                job = self._normalise(raw)
                if job is None or job["external_id"] in seen:
                    continue
                seen.add(job["external_id"])
                results.append(job)
            if len(content) < self.page_size:
                break
            total = payload.get("totalFound")
            offset += self.page_size
            if isinstance(total, int) and offset >= total:
                break
        return results

    def _normalise(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        external_id = str(raw.get("id") or "").strip()
        title = str(raw.get("name") or "").strip()
        url = str(raw.get("ref") or "").strip()
        if not external_id or not title or not url:
            return None

        location_data = raw.get("location") if isinstance(raw.get("location"), dict) else {}
        location = str(location_data.get("fullLocation") or "").strip()
        if not location:
            parts = [location_data.get(k) for k in ("city", "region", "country")]
            location = ", ".join(str(v).strip() for v in parts if v)
        employment = raw.get("typeOfEmployment")
        if isinstance(employment, dict):
            employment = employment.get("label") or employment.get("name")
        department = raw.get("department")
        if isinstance(department, dict):
            department = department.get("label") or department.get("name")

        return {
            "external_id": external_id,
            "company": self.company_name,
            "title": title,
            "location": [location] if location else [],
            "url": url,
            "description": self._extract_description(raw),
            "experience_level": None,
            "employment_type": str(employment).strip() if employment else None,
            "posted_at": self._parse_date(raw.get("releasedDate") or raw.get("createdOn")),
            "source": self.source,
            "department": str(department).strip() if department else None,
        }

    @classmethod
    def _extract_description(cls, raw: dict[str, Any]) -> str:
        job_ad = raw.get("jobAd") if isinstance(raw.get("jobAd"), dict) else {}
        sections = job_ad.get("sections") if isinstance(job_ad.get("sections"), list) else []
        chunks: list[str] = []
        for section in sections:
            if not isinstance(section, dict):
                continue
            heading = str(section.get("title") or "").strip()
            text = str(section.get("text") or "").strip()
            if heading:
                chunks.append(heading)
            if text:
                chunks.append(cls._html_to_text(text))
        return "\n".join(chunks).strip()

    @staticmethod
    def _parse_date(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            text = str(value).strip().replace("Z", "+00:00")
            parsed = datetime.fromisoformat(text)
            return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
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
