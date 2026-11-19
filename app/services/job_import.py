"""Add one job by pasting its link (for example a referral job from a company with no public job list).

Two readers, both reading only the single page you point at:
- Workday job pages: the board's own public JSON for that one job.
- Any other career page: the schema.org "JobPosting" data most career sites publish for search engines.
Nothing is guessed: if the page offers neither, the import says so and you can still track the job by hand.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (JobPilot personal job import)"
MAX_BYTES = 3_000_000


class ImportError_(Exception):
    """A readable reason the link could not be imported."""


def check_public_https(url: str) -> str:
    """Only public https pages are fetched (never localhost or a private network address)."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme != "https" or not parsed.hostname:
        raise ImportError_("Paste the full https:// link to the job posting.")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parsed.hostname, 443)}
    except socket.gaierror as exc:
        raise ImportError_("That address could not be found.") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:  # loopback, private, link-local and similar (NAT64 addresses of public sites are global)
            raise ImportError_("That address is not a public web page.")
    return parsed.geturl()


def _text(html: str | None) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(str(html), "html.parser")
    for tag in soup.find_all(["br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol"]):
        tag.insert_after("\n")
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", soup.get_text(""))).strip()


def _when(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None) if value else None
    except ValueError:
        return None


def _workday(url: str, get) -> dict[str, Any] | None:
    parsed = urlparse(url)
    if not (parsed.hostname or "").endswith(".myworkdayjobs.com"):
        return None
    tenant = parsed.hostname.split(".")[0]
    parts = [p for p in parsed.path.split("/") if p]
    if parts and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", parts[0]):
        parts = parts[1:]  # a locale prefix such as en-US
    if len(parts) < 3 or "job" not in parts:
        return None
    site, rest = parts[0], parts[parts.index("job"):]
    api = f"https://{parsed.hostname}/wday/cxs/{tenant}/{site}/{'/'.join(rest)}"
    response = get(api, headers={"Accept": "application/json", "User-Agent": USER_AGENT}, timeout=30)
    if response.status_code == 404:
        raise ImportError_("That job was not found on the company's Workday board. It may have been taken down.")
    response.raise_for_status()
    info = (response.json() or {}).get("jobPostingInfo") or {}
    title = str(info.get("title") or "").strip()
    if not title:
        return None
    company = ((response.json().get("hiringOrganization") or {}).get("name")) or tenant.replace("-", " ").title()
    locations = [str(info.get("location") or "").strip(), *[str(x).strip() for x in (info.get("additionalLocations") or [])]]
    return {
        "title": title, "company": str(company).strip(), "location": [loc for loc in locations if loc],
        "description": _text(info.get("jobDescription")), "external_id": str(info.get("jobReqId") or info.get("id") or ""),
        "posted_at": _when(info.get("startDate")), "employment_type": str(info.get("timeType") or "").strip() or None,
        "url": str(info.get("externalUrl") or url),
    }


def _json_ld(html: str, url: str) -> dict[str, Any] | None:
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or script.get_text() or "")
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict) and isinstance(node.get("@graph"), list):
                stack.extend(node["@graph"])
            if not isinstance(node, dict) or "JobPosting" not in str(node.get("@type")):
                continue
            org = node.get("hiringOrganization")
            company = org.get("name") if isinstance(org, dict) else org
            places = node.get("jobLocation") or []
            places = places if isinstance(places, list) else [places]
            locations = []
            for place in places:
                address = (place or {}).get("address") or {}
                if isinstance(address, dict):
                    locations.append(", ".join(str(address.get(k)) for k in ("addressLocality", "addressRegion", "addressCountry") if address.get(k)))
            if str(node.get("jobLocationType") or "").upper() == "TELECOMMUTE":
                locations.append("Remote")
            identifier = node.get("identifier")
            external = identifier.get("value") if isinstance(identifier, dict) else identifier
            return {
                "title": str(node.get("title") or "").strip(), "company": str(company or "").strip(),
                "location": [loc for loc in locations if loc], "description": _text(node.get("description")),
                "external_id": str(external or ""), "posted_at": _when(node.get("datePosted")),
                "employment_type": str(node.get("employmentType") or "").strip("[]'\" ") or None, "url": url,
            }
    return None


_LEGAL_SUFFIX = re.compile(r"[\s,]+(private limited|pvt\.? ?ltd\.?|limited|ltd\.?|inc\.?|llc|gmbh|corp\.?|corporation|india)$", re.IGNORECASE)


def clean_company(name: str) -> str:
    """'52 Qualcomm India Private Limited' -> 'Qualcomm' (the name a person and their email would use)."""
    cleaned = re.sub(r"^\d+\s+", "", name.strip())
    for _ in range(3):
        shorter = _LEGAL_SUFFIX.sub("", cleaned).strip(" ,")
        if shorter == cleaned or not shorter:
            break
        cleaned = shorter
    return cleaned or name.strip()


def fetch_job(url: str, get=requests.get) -> dict[str, Any]:
    """Read one job from its page. Raises ImportError_ with a readable reason when it cannot."""
    url = check_public_https(url)
    try:
        job = _workday(url, get)
        if job is None:
            response = get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
            if response.status_code in (404, 410):
                raise ImportError_("That page was not found. The job may have been taken down.")
            response.raise_for_status()
            job = _json_ld(response.text[:MAX_BYTES], url)
    except ImportError_:
        raise
    except requests.RequestException as exc:
        raise ImportError_(f"The page could not be read ({type(exc).__name__}).") from exc
    if not job or not job["title"] or not job["company"]:
        raise ImportError_(
            "This page does not publish its job details in a form JobPilot can read. "
            "Add the job by hand from the Applications screen instead."
        )
    job["company"] = clean_company(job["company"])
    if not job["external_id"]:
        job["external_id"] = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    return job
