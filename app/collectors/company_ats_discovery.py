from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


# Detection is deliberately broader than the set of implemented connectors.
# A detected URL is evidence about the employer's ATS, not proof that JobPilot
# can call its private/public API. Unsupported providers remain discovery-only.
ATS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("greenhouse", re.compile(r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/([^/?#]+)", re.I)),
    ("lever", re.compile(r"jobs(?:\.eu)?\.lever\.co/([^/?#]+)", re.I)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([^/?#]+)", re.I)),
    ("smartrecruiters", re.compile(r"(?:jobs|careers)\.smartrecruiters\.com/([^/?#]+)", re.I)),
    ("workable", re.compile(r"apply\.workable\.com/([^/?#]+)", re.I)),
    ("icims", re.compile(r"([a-z0-9-]+)\.icims\.com/jobs", re.I)),
    ("successfactors", re.compile(r"([a-z0-9-]+)\.successfactors\.(?:com|eu|net)/career", re.I)),
    ("taleo", re.compile(r"([a-z0-9-]+)\.taleo\.net/careersection", re.I)),
    ("jobvite", re.compile(r"jobs\.jobvite\.com/([^/?#]+)", re.I)),
    ("bamboohr", re.compile(r"([a-z0-9-]+)\.bamboohr\.com/careers", re.I)),
    ("recruitee", re.compile(r"([a-z0-9-]+)\.recruitee\.com", re.I)),
    ("teamtailor", re.compile(r"([a-z0-9-]+)\.teamtailor\.com/jobs", re.I)),
    ("eightfold", re.compile(r"([a-z0-9-]+)\.eightfold\.ai/careers", re.I)),
    ("phenom", re.compile(r"([a-z0-9-]+)\.phenompeople\.com", re.I)),
)
ORACLE_HCM_RE = re.compile(
    r"(?P<host>[a-z0-9-]+\.fa\.[a-z0-9-]+\.oraclecloud\.com)/hcmUI/CandidateExperience/(?P<language>[a-z]{2})/sites/(?P<site>[A-Za-z0-9_-]+)",
    re.I,
)
WORKDAY_RE = re.compile(
    r"(?P<host>[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com)/(?P<site>[A-Za-z0-9_-]+)",
    re.I,
)


def detect_ats_links(html: str, page_url: str) -> list[dict[str, str]]:
    """Detect ATS board URLs embedded in a public careers page."""
    soup = BeautifulSoup(html or "", "html.parser")
    candidates: set[str] = set()
    for node in soup.find_all(["a", "iframe", "script"]):
        value = node.get("href") or node.get("src")
        if value:
            candidates.add(urljoin(page_url, str(value).strip()))
    # Some sites place the ATS URL in JSON hydration script text, not anchors.
    for match in re.findall(r"https?://[^\s\"'<>\\]+", html or "", re.I):
        candidates.add(match.rstrip("),;]"))

    found: dict[tuple[str, str], dict[str, str]] = {}
    for url in candidates:
        for provider, pattern in ATS_PATTERNS:
            match = pattern.search(url)
            if match:
                identifier = match.group(1)
                key = (provider, identifier.casefold())
                found[key] = {"provider": provider, "identifier": identifier, "url": url}
        oracle = ORACLE_HCM_RE.search(url)
        if oracle:
            host = oracle.group("host")
            language = oracle.group("language")
            site = oracle.group("site")
            key = ("oracle_hcm", f"{host}:{site}".casefold())
            found[key] = {
                "provider": "oracle_hcm",
                "identifier": f"{host}:{site}",
                "base_url": f"https://{host}",
                "language": language,
                "site_number": site,
                "url": url,
            }
        workday = WORKDAY_RE.search(url)
        if workday:
            host = workday.group("host")
            tenant = host.split(".", 1)[0]
            site = workday.group("site")
            key = ("workday", f"{tenant}:{site}".casefold())
            found[key] = {
                "provider": "workday",
                "identifier": f"{tenant}:{site}",
                "host": f"https://{host}",
                "tenant": tenant,
                "site": site,
                "url": url,
            }
    return sorted(found.values(), key=lambda item: (item["provider"], item["identifier"].casefold()))


def discover_company_source(
    company: dict[str, Any],
    *,
    timeout: int = 20,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    url = str(company.get("careers_url") or "").strip()
    if not url:
        return {"company_id": company.get("id"), "company": company.get("name"), "status": "missing_careers_url", "sources": []}
    http = session or requests.Session()
    try:
        response = http.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": "JobPilot/1.0 (public careers-source discovery)", "Accept": "text/html,application/xhtml+xml"},
        )
        response.raise_for_status()
        source_html = response.text
        sources = detect_ats_links(source_html, response.url)
        if sources:
            status = "ats_detected"
        elif "myworkdayjobs.com" in response.url:
            status = "workday_site_detected"
            parsed = urlparse(response.url)
            match = WORKDAY_RE.search(parsed.netloc + parsed.path)
            sources = []
            if match:
                tenant = match.group("host").split(".", 1)[0]
                site = match.group("site")
                sources.append({"provider": "workday", "identifier": f"{tenant}:{site}", "host": f"https://{match.group('host')}", "tenant": tenant, "site": site, "url": response.url})
        else:
            status = "no_static_ats_link_found"
        return {
            "company_id": company.get("id"),
            "company": company.get("name"),
            "careers_url": url,
            "resolved_url": response.url,
            "http_status": response.status_code,
            "status": status,
            "sources": sources,
        }
    except requests.RequestException as exc:
        return {
            "company_id": company.get("id"),
            "company": company.get("name"),
            "careers_url": url,
            "status": "request_failed",
            "error": f"{type(exc).__name__}: {exc}",
            "sources": [],
        }


def integration_config_from_source(source: dict[str, str]) -> dict[str, Any] | None:
    """Convert a detected public ATS link into a safe, unverified registry mapping."""
    provider = str(source.get("provider") or "").strip().casefold()
    identifier = str(source.get("identifier") or "").strip()
    if not provider or not identifier:
        return None

    settings: dict[str, Any]
    if provider == "greenhouse":
        settings = {"board_token": identifier}
    elif provider == "lever":
        settings = {"site": identifier, "region": "global"}
    elif provider == "ashby":
        settings = {"board_name": identifier}
    elif provider == "smartrecruiters":
        settings = {"company_identifier": identifier}
    elif provider == "workday":
        settings = {
            "tenant": str(source.get("tenant") or ""),
            "site": str(source.get("site") or ""),
            "host": str(source.get("host") or ""),
            "locale": "en-US",
        }
    elif provider == "oracle_hcm":
        settings = {
            "base_url": str(source.get("base_url") or ""),
            "site_number": str(source.get("site_number") or ""),
            "language": str(source.get("language") or "en"),
            "country_code": "IN",
        }
    else:
        return None

    if not all(str(value).strip() for value in settings.values()):
        return None
    return {
        "provider": provider,
        "status": "configured_needs_live_validation",
        "verified": False,
        "settings": settings,
        "discovered_url": str(source.get("url") or ""),
        "notes": "Detected from the company's official careers page. Run a read-only dry-run before setting verified=true.",
    }
