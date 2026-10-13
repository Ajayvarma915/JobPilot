from __future__ import annotations

from html import unescape
from typing import Any
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from app.collectors.base import JobCollector


class GreenhouseCollector(JobCollector):
    """Collect published jobs from one public Greenhouse board."""

    API_ROOT = "https://boards-api.greenhouse.io/v1/boards"

    def __init__(
        self,
        board_token: str,
        company_name: str,
        *,
        website: str | None = None,
        careers_url: str | None = None,
        timeout: int = 30,
    ) -> None:
        token = board_token.strip()
        name = company_name.strip()

        if not token:
            raise ValueError("Greenhouse board_token cannot be empty.")

        if not name:
            raise ValueError("Greenhouse company_name cannot be empty.")

        self.board_token = token
        self.company_name = name
        self.website = website
        self.careers_url = careers_url
        self.timeout = timeout
        self.source = f"greenhouse:{self.board_token.casefold()}"

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "JobPilot/0.1 (personal job discovery)",
            }
        )

    def collect(self) -> list[dict[str, Any]]:
        """Fetch all published jobs from the configured public board."""
        url = (
            f"{self.API_ROOT}/"
            f"{quote(self.board_token, safe='')}/jobs"
        )

        response = self.session.get(
            url,
            params={"content": "true"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()

        results: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        seen_urls: set[str] = set()

        for raw_job in payload.get("jobs", []):
            if not isinstance(raw_job, dict):
                continue

            job = self._normalize_job(raw_job)

            if job is None:
                continue

            external_id = job.get("external_id")
            job_url = job.get("url")

            if external_id:
                identity = str(external_id)

                if identity in seen_ids:
                    continue

                seen_ids.add(identity)

            elif job_url:
                if job_url in seen_urls:
                    continue

                seen_urls.add(job_url)

            else:
                continue

            results.append(job)

        return results

    def _normalize_job(
        self,
        raw_job: dict[str, Any],
    ) -> dict[str, Any] | None:
        title = str(raw_job.get("title") or "").strip()
        job_url = str(raw_job.get("absolute_url") or "").strip()
        external_id = raw_job.get("id")

        if not title or not job_url or external_id is None:
            return None

        return {
            "external_id": str(external_id),
            "company": self.company_name,
            "title": title,
            "location": self._extract_locations(raw_job),
            "url": job_url,
            "description": self._html_to_text(
                str(raw_job.get("content") or "")
            ),
            "experience_level": None,
            "employment_type": self._employment_type(raw_job),
            "posted_at": None,
            "source": self.source,
        }

    @staticmethod
    def _extract_locations(
        raw_job: dict[str, Any],
    ) -> list[str]:
        locations: list[str] = []

        main_location = raw_job.get("location")

        if isinstance(main_location, dict):
            name = str(main_location.get("name") or "").strip()

            if name:
                locations.append(name)

        offices = raw_job.get("offices")

        if isinstance(offices, list):
            for office in offices:
                if not isinstance(office, dict):
                    continue

                location = str(
                    office.get("location") or office.get("name") or ""
                ).strip()

                if location:
                    locations.append(location)

        return list(dict.fromkeys(locations))

    @staticmethod
    def _employment_type(
        raw_job: dict[str, Any],
    ) -> str | None:
        # Greenhouse does not expose employment type in a universally
        # consistent standard field. Only use an explicit metadata value.
        metadata = raw_job.get("metadata")

        if isinstance(metadata, list):
            for item in metadata:
                if not isinstance(item, dict):
                    continue

                name = str(
                    item.get("name") or item.get("id") or ""
                ).casefold()

                value = str(item.get("value") or "").strip()

                if "employment" in name and value:
                    return value

        return None

    @staticmethod
    def _html_to_text(value: str) -> str:
        """Decode escaped HTML and convert job content to readable text."""
        text = value

        for _ in range(3):
            decoded = unescape(text)

            if decoded == text:
                break

            text = decoded

        soup = BeautifulSoup(text, "html.parser")

        for node in soup(["script", "style"]):
            node.decompose()

        lines = [
            " ".join(line.split())
            for line in soup.get_text("\n").splitlines()
            if line.strip()
        ]

        return "\n".join(lines)