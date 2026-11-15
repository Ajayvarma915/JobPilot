from __future__ import annotations

import re
from html import unescape
from typing import Any

import requests
from bs4 import BeautifulSoup

from app.collectors.base import JobCollector


class AtlassianCareersCollector(JobCollector):
    """Collect listings from Atlassian's own public careers feed.

    The feed is the JSON that atlassian.com/company/careers loads itself
    (https://www.atlassian.com/endpoint/careers/listings), so ownership is
    established by the domain. One request returns every listing with its
    overview, responsibilities and qualifications, so no per-job detail
    request is needed. Rows can repeat the same id; they are deduplicated.
    """

    LISTINGS_URL = "https://www.atlassian.com/endpoint/careers/listings"

    def __init__(self, company_name: str = "Atlassian", *, timeout: int = 60) -> None:
        self.company_name = company_name.strip()
        if not self.company_name:
            raise ValueError("Atlassian company_name is required.")
        self.timeout = timeout
        self.source = "atlassian_careers"
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "JobPilot/1.0 (personal job discovery; public career postings)",
        })

    def collect(self) -> list[dict[str, Any]]:
        response = self.session.get(self.LISTINGS_URL, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Unexpected Atlassian careers response: expected a list.")

        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in payload:
            if not isinstance(raw, dict):
                continue
            job = self._normalize(raw)
            if job is None or job["external_id"] in seen:
                continue
            seen.add(job["external_id"])
            results.append(job)
        return results

    def _normalize(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        external_id = str(raw.get("id") or "").strip()
        title = str(raw.get("title") or "").strip()
        if not external_id or not title:
            return None

        portal = raw.get("portalJobPost") if isinstance(raw.get("portalJobPost"), dict) else {}
        url = str(portal.get("portalUrl") or "").strip() or str(raw.get("applyUrl") or "").strip()
        if not url:
            return None

        locations: list[str] = []
        raw_locations = raw.get("locations")
        if isinstance(raw_locations, list):
            for item in raw_locations:
                text = re.sub(r"\s+", " ", str(item or "")).strip()
                if text and text not in locations:
                    locations.append(text)

        # Qualifications first so the experience parser sees them even when the
        # overview is long boilerplate; sections stay clearly labelled.
        sections = [
            ("Qualifications", raw.get("qualifications")),
            ("Responsibilities", raw.get("responsibilities")),
            ("Overview", raw.get("overview")),
        ]
        parts = []
        for heading, value in sections:
            text = self._html_to_text(str(value or ""))
            if text:
                parts.append(f"{heading}:\n{text}")

        return {
            "external_id": external_id,
            "company": self.company_name,
            "title": title,
            "location": locations,
            "url": url,
            "description": "\n\n".join(parts),
            "experience_level": None,
            "employment_type": raw.get("type"),
            "posted_at": None,  # the feed only exposes an "updated" time, not a posting date
            "source": self.source,
            "department": raw.get("category"),
            "workplace_type": None,
        }

    @staticmethod
    def _html_to_text(value: str) -> str:
        soup = BeautifulSoup(unescape(value), "html.parser")
        for node in soup(["script", "style"]):
            node.decompose()
        return "\n".join(
            " ".join(line.split()) for line in soup.get_text("\n").splitlines() if line.strip()
        )
