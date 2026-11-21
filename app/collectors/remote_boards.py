"""Remote job boards with a public feed: Remotive, Remote OK, Himalayas, We Work Remotely, Y Combinator's
public jobs pages, Jobicy and Working Nomads.

These boards list remote jobs from many employers, so every job carries its own company. Each
collector returns the same job dictionaries as the company connectors, with a location written as
"Remote - <where it can be worked from>" so the normal eligibility rules and the Remote jobs tab
can use it.

Terms: Remote OK asks that anything shown from its feed links back to Remote OK and names it as the
source. JobPilot keeps each job's own link and source label ("remoteok") for that reason; do not
republish the feed. Jobicy asks for a credit and a direct link: jobs keep their own Jobicy link.
Y Combinator's own robots.txt allows /jobs, and only public pages are read, politely (a short pause
between requests). YC's "Work at a Startup" site needs a login and is not touched.
Wellfound is deliberately not here: it has no public feed, sits behind a bot check (Cloudflare
Turnstile) and does not allow scraping.
"""
from __future__ import annotations

import json
import re
import time
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

    def __init__(self, *, timeout: int = 40, session: requests.Session | None = None, fetch_details: bool = True) -> None:
        self.timeout = timeout
        # False when only "is this job still listed" is needed: collectors then skip per-job page requests.
        self.fetch_details = fetch_details
        self.session = session or with_retries(requests.Session())
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

    @property
    def source(self) -> str:
        return f"remote_board:{self.board}"

    def _job(self, *, external_id: Any, company: Any, title: Any, region: str, url: Any, description: str,
             posted: Any = None, employment_type: Any = None, workplace: str = "remote") -> dict[str, Any] | None:
        external_id, company, title, url = (str(value or "").strip() for value in (external_id, company, title, url))
        if not (external_id and company and title and url):
            return None
        return {
            "external_id": f"{self.board}-{external_id}",
            "company": company,
            "title": title,
            "location": _location(region),
            "workplace_type": workplace,
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

    SEARCH_URL = "https://himalayas.app/jobs/api/search"
    SEARCH_QUERIES = ("software engineer", "backend developer", "frontend developer", "full stack developer", "devops engineer",
                      "data engineer", "machine learning engineer", "python developer", "node.js developer", "java developer")
    SEARCH_VARIANTS = ({"country": "India"}, {"worldwide": "true"})

    def __init__(self, *, max_pages: int = 6, page_size: int = 100, searches: tuple[str, ...] | None = None,
                 search_pages: int = 3, pause: float = 0.2, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.max_pages = max_pages
        self.page_size = page_size
        self.searches = self.SEARCH_QUERIES if searches is None else searches
        self.search_pages = search_pages
        self.pause = pause

    def _from_raw(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        link = raw.get("applicationLink") or raw.get("guid")
        return self._job(
            external_id=raw.get("guid") or link, company=raw.get("companyName"), title=raw.get("title"),
            region=_region(raw.get("locationRestrictions")), url=link,
            description=_text(raw.get("description") or raw.get("excerpt")), posted=raw.get("pubDate"),
            employment_type=raw.get("employmentType"),
        )

    def _search(self) -> list[dict[str, Any]]:
        """Himalayas' search lets you ask for roles open to India and for worldwide roles directly."""
        found: dict[str, dict[str, Any]] = {}
        for query in self.searches:
            for variant in self.SEARCH_VARIANTS:
                for page in range(1, self.search_pages + 1):
                    response = self.session.get(self.SEARCH_URL, params={"q": query, **variant, "page": page}, timeout=self.timeout)
                    response.raise_for_status()
                    listed = response.json().get("jobs") or []
                    for raw in listed:
                        job = self._from_raw(raw)
                        if job:
                            found.setdefault(job["external_id"], job)
                    if len(listed) < 20:
                        break
                    time.sleep(self.pause)
        return list(found.values())

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
                job = self._from_raw(raw)
                if job:
                    jobs.append(job)
            cursor = payload.get("nextCursor")
            if not cursor:
                break
        if self.fetch_details and self.searches:  # the search is for finding jobs; the "still listed?" check only needs the feed
            seen = {job["external_id"] for job in jobs}
            jobs.extend(job for job in self._search() if job["external_id"] not in seen)
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


class YCombinatorCollector(_BoardCollector):
    """Startup jobs from ycombinator.com/jobs (public pages; YC's robots.txt allows /jobs).

    Reads the role pages (software, backend, frontend, full stack ...) and, only for jobs that already pass
    a title and location pre-check, the job's own page for its description. YC lists the minimum experience
    for each job, which is passed on as the job's stated requirement.
    """

    board = "ycombinator"
    BASE = "https://www.ycombinator.com"
    ROLES = ("software-engineer", "backend-engineer", "frontend-engineer", "full-stack-engineer",
             "machine-learning-engineer", "devops-engineer", "ios-engineer", "android-engineer", "data-engineer")
    # Extra location pages, sampled more than once (each visit shows a different sample of the jobs).
    LOCATIONS = ("remote", "remote", "remote", "remote")

    def __init__(self, *, pages_per_role: int = 3, max_details: int = 80, pause: float = 0.25, **kwargs: Any) -> None:
        injected = kwargs.get("session") is not None
        super().__init__(**kwargs)
        self.pages_per_role = pages_per_role
        self.max_details = max_details
        self.pause = pause
        self.session.headers.update({"Accept": "text/html"})
        # YC shows a different random sample of its jobs on every visit, and a kept-open connection keeps
        # returning the same sample. A fresh connection per page gives a new sample, and the union over
        # several pages covers far more of the list.
        self._get = self.session.get if injected else (lambda url, **kw: requests.get(url, headers=dict(self.session.headers), **kw))

    def _props(self, url: str) -> dict[str, Any] | None:
        response = self._get(url, timeout=self.timeout)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        found = re.search(r'data-page="([^"]+)"', response.text)
        if not found:
            return None
        try:
            return json.loads(unescape(found.group(1))).get("props")
        except ValueError:
            return None

    @staticmethod
    def locations(raw: str) -> tuple[list[str], bool]:
        """YC writes 'HQ / New York, NY, US / Remote (US)'. Returns (location entries, any remote entry)."""
        entries = [part.strip() for part in re.split(r"\s+/\s+", raw or "") if part.strip() and part.strip().upper() != "HQ"]
        out: list[str] = []
        remote = False
        for entry in entries:
            if re.match(r"(?i)^remote\b", entry):
                remote = True
                detail = re.sub(r"(?i)^remote\s*", "", entry).strip(" ()")
                out.append(f"Remote - {_region(detail)}" if detail else "Remote")
            else:
                out.append(entry)
        return out, remote

    @staticmethod
    def experience_text(minimum: Any) -> str:
        text = str(minimum or "").strip()
        match = re.search(r"(\d+)\s*\+?\s*years?", text, re.IGNORECASE)
        if match:
            return f"Minimum qualifications: {match.group(1)}+ years of experience (stated in the YC listing).\n"
        if re.search(r"any|new grad", text, re.IGNORECASE):
            return "Minimum qualifications: 0 years of experience (the YC listing says new graduates are welcome).\n"
        return ""

    def _worth_details(self, post: dict[str, Any], places: list[str]) -> bool:
        """Cheap pre-check so a description is only fetched for jobs that could still be accepted."""
        from app.services.target_role_policy import is_india_or_remote_eligible, is_target_software_role

        if not is_target_software_role(str(post.get("title") or ""), self.experience_text(post.get("minExperience")))[0]:
            return False
        return is_india_or_remote_eligible({"location": places, "workplace_type": "remote"})[0]

    def _description(self, post: dict[str, Any]) -> str:
        try:
            props = self._props(self.BASE + str(post["url"]))
        except requests.RequestException:
            return ""
        job = (props or {}).get("job") or {}
        return _text(str(job.get("description") or ""))

    def collect(self) -> list[dict[str, Any]]:
        posts: dict[Any, dict[str, Any]] = {}
        urls = [f"{self.BASE}/jobs/role/{role}" + ("" if page == 1 else f"?page={page}")
                for role in self.ROLES for page in range(1, self.pages_per_role + 1)]
        urls += [f"{self.BASE}/jobs/location/{slug}" + ("" if n == 0 else f"?page={n + 1}") for n, slug in enumerate(self.LOCATIONS)]
        for url in urls:
            props = self._props(url)
            for post in (props or {}).get("jobPostings") or []:
                posts.setdefault(post.get("id"), post)
            time.sleep(self.pause)
        jobs: list[dict[str, Any]] = []
        details_left = self.max_details if self.fetch_details else 0
        for post in posts.values():
            places, remote = self.locations(str(post.get("location") or ""))
            stated = self.experience_text(post.get("minExperience"))
            description = ""
            if details_left > 0 and self._worth_details(post, places):
                description = self._description(post)
                details_left -= 1
                time.sleep(self.pause)
            job = self._job(
                external_id=post.get("id"), company=post.get("companyName"), title=post.get("title"), region="",
                url=self.BASE + str(post.get("url") or ""), description=(stated + description).strip() or str(post.get("title") or ""),
                employment_type=post.get("type"), workplace="remote" if remote else "onsite",
            )
            if job:
                job["location"] = places or ["Remote"]
                jobs.append(job)
        return jobs


class JobicyCollector(_BoardCollector):
    board = "jobicy"
    URL = "https://jobicy.com/api/v2/remote-jobs"

    def collect(self) -> list[dict[str, Any]]:
        response = self.session.get(self.URL, params={"count": 50, "geo": "anywhere", "industry": "dev"}, timeout=self.timeout)
        response.raise_for_status()
        jobs = []
        for raw in response.json().get("jobs") or []:
            job = self._job(
                external_id=raw.get("id"), company=raw.get("companyName"), title=raw.get("jobTitle"), region=_region(raw.get("jobGeo")),
                url=raw.get("url"), description=_text(raw.get("jobDescription") or raw.get("jobExcerpt")), posted=raw.get("pubDate"),
                employment_type=", ".join(raw.get("jobType") or []) or None,
            )
            if job:
                jobs.append(job)
        return jobs


class WorkingNomadsCollector(_BoardCollector):
    board = "workingnomads"
    URL = "https://www.workingnomads.com/api/exposed_jobs/"

    def collect(self) -> list[dict[str, Any]]:
        response = self.session.get(self.URL, timeout=self.timeout)
        response.raise_for_status()
        jobs = []
        for raw in response.json():
            if str(raw.get("category_name") or "").casefold() != "development":
                continue
            found = re.search(r"/(\d+)/?$", str(raw.get("url") or ""))
            job = self._job(
                external_id=found.group(1) if found else raw.get("url"), company=raw.get("company_name"), title=raw.get("title"),
                region=_region(raw.get("location")), url=raw.get("url"), description=_text(raw.get("description")), posted=raw.get("pub_date"),
            )
            if job:
                jobs.append(job)
        return jobs


COLLECTORS: dict[str, type[_BoardCollector]] = {
    "remotive": RemotiveCollector,
    "remoteok": RemoteOkCollector,
    "himalayas": HimalayasCollector,
    "weworkremotely": WeWorkRemotelyCollector,
    "ycombinator": YCombinatorCollector,
    "jobicy": JobicyCollector,
    "workingnomads": WorkingNomadsCollector,
}
