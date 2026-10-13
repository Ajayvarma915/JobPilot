from __future__ import annotations

from html import unescape
from typing import Any
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from app.collectors.base import JobCollector


class LeverCollector(JobCollector):
    """Collect published postings from Lever's public postings API."""

    API_ROOTS = {
        "global": "https://api.lever.co/v0/postings",
        "eu": "https://api.eu.lever.co/v0/postings",
    }

    def __init__(
        self,
        site: str,
        company_name: str,
        *,
        region: str = "global",
        website: str | None = None,
        careers_url: str | None = None,
        timeout: int = 30,
    ) -> None:
        clean_site = site.strip()
        clean_name = company_name.strip()

        if not clean_site:
            raise ValueError("Lever site cannot be empty.")

        if not clean_name:
            raise ValueError("Lever company_name cannot be empty.")

        if region not in self.API_ROOTS:
            raise ValueError("Lever region must be 'global' or 'eu'.")

        self.site = clean_site
        self.company_name = clean_name
        self.region = region
        self.website = website
        self.careers_url = careers_url
        self.timeout = timeout
        self.source = f"lever:{self.region}:{self.site.casefold()}"

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "JobPilot/0.1 (personal job discovery)",
            }
        )

    def collect(self) -> list[dict[str, Any]]:
        """Fetch published job postings for the configured Lever site."""
        url = (
            f"{self.API_ROOTS[self.region]}/"
            f"{quote(self.site, safe='')}"
        )

        response = self.session.get(
            url,
            params={"mode": "json", "limit": 1000},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()

        if not isinstance(payload, list):
            raise ValueError(
                f"Unexpected Lever API response for site '{self.site}'."
            )

        results: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for raw_job in payload:
            if not isinstance(raw_job, dict):
                continue

            job = self._normalize_job(raw_job)

            if job is None:
                continue

            external_id = job["external_id"]

            if external_id in seen_ids:
                continue

            seen_ids.add(external_id)
            results.append(job)

        return results

    def _normalize_job(
        self,
        raw_job: dict[str, Any],
    ) -> dict[str, Any] | None:
        external_id = raw_job.get("id")

        title = str(
            raw_job.get("text") or raw_job.get("title") or ""
        ).strip()

        job_url = str(
            raw_job.get("hostedUrl") or raw_job.get("applyUrl") or ""
        ).strip()

        if external_id is None or not title or not job_url:
            return None

        categories = raw_job.get("categories")

        if not isinstance(categories, dict):
            categories = {}

        location = str(categories.get("location") or "").strip()

        employment_type = str(
            categories.get("commitment")
            or categories.get("employmentType")
            or ""
        ).strip() or None

        return {
            "external_id": str(external_id),
            "company": self.company_name,
            "title": title,
            "location": [location] if location else [],
            "url": job_url,
            "description": self._extract_description(raw_job),
            "experience_level": None,
            "employment_type": employment_type,
            "posted_at": None,
            "source": self.source,
            "workplace_type": raw_job.get("workplaceType"),
            "team": categories.get("team"),
            "department": categories.get("department"),
        }

    @classmethod
    def _extract_description(
        cls,
        raw_job: dict[str, Any],
    ) -> str:
        parts: list[str] = []

        description_plain = str(
            raw_job.get("descriptionPlain") or ""
        ).strip()

        if description_plain:
            parts.append(description_plain)
        else:
            description_html = str(
                raw_job.get("description") or ""
            ).strip()

            if description_html:
                parts.append(cls._html_to_text(description_html))

        lists = raw_job.get("lists")

        if isinstance(lists, list):
            for item in lists:
                if not isinstance(item, dict):
                    continue

                heading = str(item.get("text") or "").strip()
                content = str(item.get("content") or "").strip()
                content_text = cls._html_to_text(content) if content else ""

                if heading:
                    parts.append(heading)

                if content_text:
                    parts.append(content_text)

        additional_plain = str(
            raw_job.get("additionalPlain") or ""
        ).strip()

        if additional_plain:
            parts.append(additional_plain)
        elif raw_job.get("additional"):
            parts.append(
                cls._html_to_text(str(raw_job["additional"]))
            )

        return "\n".join(part for part in parts if part).strip()

    @staticmethod
    def _html_to_text(value: str) -> str:
        text = unescape(value)
        soup = BeautifulSoup(text, "html.parser")

        for node in soup(["script", "style"]):
            node.decompose()

        return "\n".join(
            " ".join(line.split())
            for line in soup.get_text("\n").splitlines()
            if line.strip()
        )