"""Remote job boards with a public feed: Remotive, Remote OK, Himalayas and We Work Remotely.

These boards list remote jobs from many employers, so every job carries its own company. Each
collector returns the same job dictionaries as the company connectors, with a location written as
"Remote - <where it can be worked from>" so the normal eligibility rules and the Remote jobs tab
can use it.

Terms: Remote OK asks that anything shown from its feed links back to Remote OK and names it as the
source. JobPilot keeps each job's own link and source label ("remoteok") for that reason; do not
republish the feed. Wellfound is deliberately not here: it has no public feed, sits behind a bot
check and does not allow scraping.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html import unescape
from typing import Any

import requests
from bs4 import BeautifulSoup

from app.collectors.base import JobCollector
from app.collectors.http_retry import with_retries

USER_AGENT = "JobPilot/1.0 (personal job discovery; links back to the source board)"
WORLDWIDE = "Worldwide"


def _text(html: str | None) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(unescape(str(html)), "html.parser")
    # Block elements become line breaks; inline tags (bold, links) stay inside their sentence.
    for tag in soup.find_all(["br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol"]):
        tag.insert_after("\n")
    text = soup.get_text("")
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


def _region(value: Any) -> str:
    """Turn a board's 'where can I work from' value into text for the location."""
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(item) for item in value if item)
    text = re.sub(r"\s+", " ", str(value or "")).strip().strip("[]'\"")
    if not text or re.search(r"\b(anywhere|worldwide|global|world)\b", text, re.IGNORECASE):
        return WORLDWIDE
    return text


def _location(region: str) -> list[str]:
    return [f"Remote - {region}"]


def _when(value: Any) -> datetime | None:
    try:
        if value in (None, ""):
            return None
        if str(value).isdigit():
            return datetime.fromtimestamp(int(value), tz=timezone.utc).replace(tzinfo=None)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, OSError, OverflowError):
        return None


class _BoardCollector(JobCollector):
    board = ""

    def __init__(self, *, timeout: int = 40, session: requests.Session | None = None) -> None:
        self.timeout = timeout
        self.session = session or with_retries(requests.Session())
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

    @property
    def source(self) -> str:
        return f"remote_board:{self.board}"

    def _job(self, *, external_id: Any, company: Any, title: Any, region: str, url: Any, description: str,
             posted: Any = None, employment_type: Any = None) -> dict[str, Any] | None:
        external_id, company, title, url = (str(value or "").strip() for value in (external_id, company, title, url))
        if not (external_id and company and title and url):
            return None
        return {
            "external_id": f"{self.board}-{external_id}",
            "company": company,
            "title": title,
            "location": _location(region),
            "workplace_type": "remote",
            "url": url,
            "description": description,
            "employment_type": str(employment_type).strip() if employment_type else None,
            "posted_at": _when(posted),
            "source": self.source,
        }


class RemotiveCollector(_BoardCollector):
    board = "remotive"
    URL = "https://remotive.com/api/remote-jobs"

    def collect(self) -> list[dict[str, Any]]:
        response = self.session.get(self.URL, params={"category": "software-dev"}, timeout=self.timeout)
        response.raise_for_status()
        jobs = []
        for raw in response.json().get("jobs") or []:
            job = self._job(
                external_id=raw.get("id"), company=raw.get("company_name"), title=raw.get("title"),
                region=_region(raw.get("candidate_required_location")), url=raw.get("url"),
                description=_text(raw.get("description")), posted=raw.get("publication_date"),
                employment_type=str(raw.get("job_type") or "").replace("_", " ").title() or None,
            )
            if job:
                jobs.append(job)
        return jobs


class RemoteOkCollector(_BoardCollector):
    board = "remoteok"
    URL = "https://remoteok.com/api"

    def collect(self) -> list[dict[str, Any]]:
        response = self.session.get(self.URL, timeout=self.timeout)
        response.raise_for_status()
        jobs = []
        for raw in response.json():
            if not isinstance(raw, dict) or not raw.get("id"):
                continue  # the first element is a legal notice, not a job
            job = self._job(
                external_id=raw.get("id"), company=raw.get("company"), title=raw.get("position"),
                region=_region(raw.get("location")), url=raw.get("url") or raw.get("apply_url"),
                description=_text(raw.get("description")), posted=raw.get("date"),
            )
            if job:
                jobs.append(job)
        return jobs


class HimalayasCollector(_BoardCollector):
    board = "himalayas"
    URL = "https://himalayas.app/jobs/api"

    def __init__(self, *, max_pages: int = 6, page_size: int = 100, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.max_pages = max_pages
        self.page_size = page_size

    def collect(self) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        cursor: str | None = None
        for _ in range(self.max_pages):
            params: dict[str, Any] = {"limit": self.page_size}
            if cursor:
                params["cursor"] = cursor
            response = self.session.get(self.URL, params=params, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
            for raw in payload.get("jobs") or []:
                link = raw.get("applicationLink") or raw.get("guid")
                job = self._job(
                    external_id=raw.get("guid") or link, company=raw.get("companyName"), title=raw.get("title"),
                    region=_region(raw.get("locationRestrictions")), url=link,
                    description=_text(raw.get("description") or raw.get("excerpt")), posted=raw.get("pubDate"),
                    employment_type=raw.get("employmentType"),
                )
                if job:
                    jobs.append(job)
            cursor = payload.get("nextCursor")
            if not cursor:
                break
        return jobs


class WeWorkRemotelyCollector(_BoardCollector):
    board = "weworkremotely"
    FEEDS = (
        "https://weworkremotely.com/categories/remote-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-front-end-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
    )

    def collect(self) -> list[dict[str, Any]]:
        jobs: dict[str, dict[str, Any]] = {}
        for feed in self.FEEDS:
            response = self.session.get(feed, timeout=self.timeout, headers={"Accept": "application/rss+xml"})
            response.raise_for_status()
            for item in ET.fromstring(response.content).iter("item"):
                def field(name: str) -> str:
                    node = item.find(name)
                    return (node.text or "").strip() if node is not None else ""

                heading = field("title")
                company, _, title = heading.partition(":")
                if not title:
                    company, title = "", heading
                url = field("link") or field("guid")
                job = self._job(
                    external_id=field("guid") or url, company=company.strip() or "Unknown company", title=title.strip(),
                    region=_region(field("region")), url=url, description=_text(field("description")),
                    posted=_rfc2822(field("pubDate")), employment_type=field("type") or None,
                )
                if job:
                    jobs[job["external_id"]] = job
        return list(jobs.values())


def _rfc2822(value: str) -> str | None:
    from email.utils import parsedate_to_datetime

    try:
        return parsedate_to_datetime(value).isoformat() if value else None
    except (TypeError, ValueError):
        return None


COLLECTORS: dict[str, type[_BoardCollector]] = {
    "remotive": RemotiveCollector,
    "remoteok": RemoteOkCollector,
    "himalayas": HimalayasCollector,
    "weworkremotely": WeWorkRemotelyCollector,
}
