from __future__ import annotations

from datetime import datetime
from html import unescape
from typing import Any
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from app.collectors.base import JobCollector


class AshbyCollector(JobCollector):
    """Collect listed jobs from Ashby's public Job Posting API."""

    API_ROOT = "https://api.ashbyhq.com/posting-api/job-board"

    def __init__(
        self,
        board_name: str,
        company_name: str,
        *,
        website: str | None = None,
        careers_url: str | None = None,
        include_compensation: bool = True,
        timeout: int = 30,
    ) -> None:
        self.board_name = board_name.strip()
        self.company_name = company_name.strip()
        if not self.board_name or not self.company_name:
            raise ValueError("Ashby board_name and company_name are required.")
        self.website = website
        self.careers_url = careers_url
        self.include_compensation = include_compensation
        self.timeout = timeout
        self.source = f"ashby:{self.board_name.casefold()}"
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "JobPilot/1.0 (personal job discovery)",
        })

    def collect(self) -> list[dict[str, Any]]:
        url = f"{self.API_ROOT}/{quote(self.board_name, safe='')}"
        response = self.session.get(
            url,
            params={"includeCompensation": str(self.include_compensation).lower()},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise ValueError(f"Unexpected Ashby response for board '{self.board_name}'.")

        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in payload["jobs"]:
            if not isinstance(raw, dict) or raw.get("isListed") is False:
                continue
            job = self._normalise(raw)
            if job is None or job["external_id"] in seen:
                continue
            seen.add(job["external_id"])
            results.append(job)
        return results

    def _normalise(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        title = str(raw.get("title") or "").strip()
        job_id = str(raw.get("jobId") or raw.get("id") or "").strip()
        job_url = str(raw.get("jobUrl") or "").strip()
        if not title or not job_id or not job_url:
            return None

        locations: list[str] = []
        primary = str(raw.get("location") or "").strip()
        if primary:
            locations.append(primary)
        secondary = raw.get("secondaryLocations")
        if isinstance(secondary, list):
            for item in secondary:
                if isinstance(item, dict):
                    value = str(item.get("location") or "").strip()
                else:
                    value = str(item or "").strip()
                if value and value not in locations:
                    locations.append(value)

        description = str(raw.get("descriptionPlain") or "").strip()
        if not description:
            description = self._html_to_text(str(raw.get("descriptionHtml") or ""))

        compensation = raw.get("compensation")
        compensation_text = ""
        if isinstance(compensation, dict):
            compensation_text = str(compensation.get("summary") or "").strip()
        elif compensation:
            compensation_text = str(compensation).strip()

        posted_at = self._parse_date(raw.get("publishedAt"))
        return {
            "external_id": job_id,
            "company": self.company_name,
            "title": title,
            "location": locations,
            "url": job_url,
            "description": description,
            "experience_level": None,
            "employment_type": raw.get("employmentType"),
            "posted_at": posted_at,
            "source": self.source,
            "department": raw.get("department"),
            "team": raw.get("team"),
            "workplace_type": "remote" if raw.get("isRemote") else None,
            "compensation_text": compensation_text or None,
        }

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
        decoded = unescape(value)
        soup = BeautifulSoup(decoded, "html.parser")
        for node in soup(["script", "style"]):
            node.decompose()
        return "\n".join(
            " ".join(line.split())
            for line in soup.get_text("\n").splitlines()
            if line.strip()
        )
