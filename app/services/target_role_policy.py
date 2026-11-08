from __future__ import annotations

import re
from typing import Any


SOFTWARE_ROLE_RE = re.compile(
    r"\b(?:software engineer|software developer|software development engineer|"
    r"sde|swe|backend engineer|back-end engineer|frontend engineer|front-end engineer|"
    r"full[ -]?stack engineer|platform engineer|site reliability engineer|\bsre\b|"
    r"devops engineer|infrastructure software engineer|systems software engineer|"
    r"machine learning engineer|\bml engineer\b|ai engineer|data engineer|"
    r"security software engineer|application security engineer|product security engineer|"
    r"cloud security engineer|threat detection engineer|security automation engineer|"
    r"cybersecurity engineer|cyber security engineer|security platform engineer|"
    r"application developer|applications developer|application engineer|"
    r"mobile engineer|mobile software engineer|android engineer|ios engineer|"
    r"web developer|web engineer|embedded software engineer|firmware engineer|"
    r"cloud engineer|cloud software engineer|platform developer|"
    r"software development in test|\bsdet\b|software test automation engineer|"
    r"qa automation engineer|quality automation engineer)\b",
    re.IGNORECASE,
)

NON_SOFTWARE_ROLE_RE = re.compile(
    r"\b(?:customer support|technical support|support associate|support analyst|"
    r"account executive|account manager|sales|business development|talent acquisition|"
    r"recruiter|human resources|\bhr\b|finance|accounting|operations manager|"
    r"warehouse|supply chain|marketing|copywriter|designer|product manager|"
    r"program manager|project manager|customer success|technical account manager)\b",
    re.IGNORECASE,
)

SENIORITY_TITLE_RE = re.compile(
    r"\b(?:senior|sr\.?|staff|principal|distinguished|fellow|lead|manager|"
    r"director|head|chief|architect|vice president|vp)\b|\b(?:engineer|developer|sde)\s*(?:iii|iv|v|3|4|5)\b",
    re.IGNORECASE,
)
INTERN_TITLE_RE = re.compile(r"\b(?:intern|internship|apprentice|trainee)\b", re.IGNORECASE)

_MINIMUM_SECTION_RE = re.compile(
    r"(?:minimum qualifications|required qualifications|basic qualifications|what you'll need|what you will need|requirements)",
    re.IGNORECASE,
)
_SECTION_END_RE = re.compile(
    r"(?:preferred qualifications|nice to have|preferred skills|bonus points|about the team|responsibilities|what you'll do|what you will do)",
    re.IGNORECASE,
)


def extract_minimum_experience_years(description: str | None) -> float | None:
    """Extract a conservative minimum-experience figure from a JD.

    Uses the minimum/basic/requirements section when present; for a range such
    as '2-4 years', returns the lower bound rather than the upper bound.
    Returns None when the JD does not state a usable minimum.
    """
    text = str(description or "")
    if not text.strip():
        return None
    start = _MINIMUM_SECTION_RE.search(text)
    if start:
        tail = text[start.end():]
        end = _SECTION_END_RE.search(tail)
        text = tail[:end.start()] if end else tail[:6000]
    else:
        text = text[:6000]

    range_match = re.search(
        r"\b(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*\+?\s*years?\b",
        text,
        re.IGNORECASE,
    )
    if range_match:
        return float(range_match.group(1))

    patterns = (
        r"\b(?:at least|minimum of|min\.?|minimum)\s*(\d+(?:\.\d+)?)\s*\+?\s*years?\b",
        r"\b(\d+(?:\.\d+)?)\s*\+\s*years?\s+(?:of\s+)?(?:non[- ]internship\s+)?(?:professional\s+)?experience\b",
        r"\b(\d+(?:\.\d+)?)\s+years?\s+(?:of\s+)?(?:non[- ]internship\s+)?(?:professional\s+)?experience\b",
        r"\bexperience\s+of\s+(\d+(?:\.\d+)?)\s*\+?\s*years?\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def is_target_software_role(
    title: str,
    description: str | None = None,
    *,
    maximum_required_years: float = 2.0,
    include_sdet: bool = True,
) -> tuple[bool, str]:
    """Return (eligible, reason) for the user's 0-2 year software search."""
    clean_title = re.sub(r"\s+", " ", str(title or "")).strip()
    if not clean_title:
        return False, "missing_title"
    if NON_SOFTWARE_ROLE_RE.search(clean_title):
        return False, "non_software_title"
    if INTERN_TITLE_RE.search(clean_title):
        return False, "internship_or_trainee"
    if SENIORITY_TITLE_RE.search(clean_title):
        return False, "senior_or_lead_title"
    if not SOFTWARE_ROLE_RE.search(clean_title):
        return False, "outside_target_software_role_families"
    if not include_sdet and re.search(r"\b(?:sdet|test automation|qa automation)\b", clean_title, re.I):
        return False, "test_automation_excluded"
    minimum_years = extract_minimum_experience_years(description)
    if minimum_years is not None and minimum_years > maximum_required_years:
        return False, f"requires_{minimum_years:g}_years"
    return True, "eligible_software_role"


def filter_software_jobs(
    jobs: list[dict[str, Any]],
    *,
    maximum_required_years: float = 2.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for job in jobs:
        eligible, reason = is_target_software_role(
            str(job.get("title") or ""),
            str(job.get("description") or ""),
            maximum_required_years=maximum_required_years,
        )
        if eligible:
            accepted.append(job)
        else:
            rejected.append({"title": job.get("title"), "reason": reason})
    return accepted, rejected


INDIA_CITY_ALIASES = {
    "hyderabad", "bengaluru", "bangalore", "chennai", "pune", "mumbai",
    "gurugram", "gurgaon", "noida", "new delhi", "delhi", "kochi",
    "cochin", "thiruvananthapuram", "trivandrum", "ahmedabad", "jaipur",
    "kolkata", "indore", "bhubaneswar", "chandigarh", "mysuru", "mysore",
    "coimbatore", "vadodara", "visakhapatnam", "vizag", "nagpur", "lucknow",
    "surat", "navi mumbai", "ghaziabad", "faridabad", "tiruchirappalli",
}


def is_india_or_remote_eligible(job: dict[str, Any]) -> tuple[bool, str]:
    """Keep India-based roles and remote roles that may be available from India.

    A plain 'Remote' location is retained as unverified instead of being silently
    discarded; the dashboard/user must confirm country eligibility. Explicitly
    foreign-only roles are rejected. Salary is deliberately not a filter.
    """
    raw_location = job.get("location") or []
    if isinstance(raw_location, str):
        locations = [raw_location]
    elif isinstance(raw_location, list):
        locations = [str(value) for value in raw_location if value]
    else:
        locations = [str(raw_location)] if raw_location else []

    workplace = str(job.get("workplace_type") or "")
    description = str(job.get("description") or "")[:5000]
    location_text = " ".join(locations)
    combined = f"{location_text} {workplace}"
    normalized = re.sub(r"[^a-z0-9]+", " ", combined.casefold()).strip()
    description_norm = re.sub(r"[^a-z0-9]+", " ", description.casefold())

    if re.search(r"\bindia\b", normalized) or any(city in normalized for city in INDIA_CITY_ALIASES):
        return True, "india_location"

    foreign_markers = (
        "united states", " usa ", " uk ", "united kingdom", "canada", "germany",
        "france", "ireland", "netherlands", "poland", "singapore", "australia",
        "japan", "brazil", "mexico", "switzerland", "sweden", "spain",
        "portugal", "romania", "serbia", "israel", "united arab emirates",
    )
    padded = f" {normalized} "
    if any(marker in padded for marker in foreign_markers):
        return False, "outside_india"

    remote = bool(re.search(r"\bremote\b|work from anywhere|distributed anywhere", normalized))
    india_eligibility = bool(re.search(
        r"\b(remote|work)\b.{0,80}\b(india|worldwide|global|anywhere|multiple countries)\b|"
        r"\b(india|worldwide|global|anywhere)\b.{0,80}\b(remote|work)\b|"
        r"open to candidates in india|remote within india|india remote",
        description_norm,
    ))
    if remote and india_eligibility:
        return True, "remote_india_or_global_eligible"
    if remote:
        # A plain Remote label is worth preserving, but must not be presented as
        # confirmed India-eligible until the posting's country restriction is read.
        return True, "remote_country_eligibility_unverified"

    if not normalized:
        return False, "missing_location"

    return False, "location_not_verified_as_india"
