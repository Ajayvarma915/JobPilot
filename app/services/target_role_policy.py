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
    r"director|head|chief|architect|vice president|vp)\b|\b(?:engineer|developer|sde)\s*(?:iv|v|4|5)\b",
    re.IGNORECASE,
)
INTERN_TITLE_RE = re.compile(r"\b(?:intern|internship|apprentice|trainee)\b", re.IGNORECASE)

_MINIMUM_SECTION_RE = re.compile(
    r"(?:minimum qualifications|required qualifications|basic qualifications|minimum requirements|"
    r"required experience|what you'll need|what you will need|requirements)",
    re.IGNORECASE,
)
_SECTION_END_RE = re.compile(
    r"(?:preferred qualifications|nice to have|preferred skills|bonus points|about the team|responsibilities|what you'll do|what you will do)",
    re.IGNORECASE,
)
_PHD_RE = re.compile(r"\b(?:ph\.?\s*d\.?|doctorate|doctoral degree)\b", re.IGNORECASE)


def _minimum_qualification_text(description: str | None) -> tuple[str, bool]:
    """Return the minimum-qualification section and whether it was found."""
    text = str(description or "")
    if not text.strip():
        return "", False
    start = _MINIMUM_SECTION_RE.search(text)
    if not start:
        return text[:6000], False
    tail = text[start.end():]
    end = _SECTION_END_RE.search(tail)
    return (tail[:end.start()] if end else tail[:6000]), True


def extract_minimum_experience_years(description: str | None) -> float | None:
    """Extract a conservative minimum-experience figure from a JD.

    Uses the minimum/basic/requirements section when present; for a range such
    as '2-4 years', returns the lower bound rather than the upper bound.
    Returns None when the JD does not state a usable minimum.
    """
    text, _section_found = _minimum_qualification_text(description)
    if not text.strip():
        return None

    range_match = re.search(
        r"\b(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*\+?\s*years?\b",
        text,
        re.IGNORECASE,
    )
    if range_match:
        return float(range_match.group(1))

    patterns = (
        r"\b(?:at least|minimum of|min\.?|minimum)\s*(\d+(?:\.\d+)?)\s*\+?\s*years?\b",
        # Amazon-style wording: "3+ years of non-internship professional
        # software development experience". Descriptors may occur before
        # the final "experience" token.
        r"\b(\d+(?:\.\d+)?)\s*\+\s*years?\s+(?:of\s+)?"
        r"(?:[a-z][a-z0-9/&,-]*\s+){0,6}experience\b",
        r"\b(\d+(?:\.\d+)?)\s+years?\s+(?:of\s+)?"
        r"(?:[a-z][a-z0-9/&,-]*\s+){0,6}experience\b",
        r"\bexperience\s+of\s+(\d+(?:\.\d+)?)\s*\+?\s*years?\b",
        # Some listings express tenure as a duration in a named role rather
        # than using the word "experience", e.g. "4 years in a Salesforce
        # Developer or Architect role". Keep the search inside minimum
        # qualifications so unrelated dates/tenure elsewhere are not used.
        r"\b(\d+(?:\.\d+)?)\s*\+?\s*years?\s+(?:in|as)\s+[^.;\n]{1,140}?\b(?:role|position|capacity|developer|engineer|architect)\b",
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
    if _PHD_RE.search(clean_title):
        return False, "phd_required_or_phd_targeted_title"
    minimum_text, has_minimum_section = _minimum_qualification_text(description)
    if has_minimum_section and _PHD_RE.search(minimum_text):
        return False, "phd_required_in_minimum_qualifications"
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

    # Some ATS feeds encode countries with ISO alpha-2 prefixes, for example
    # "US, WA, Seattle" or "IN, TS, Hyderabad". Treat a code as a country only
    # at the start/end of a location component, not in the middle (where it
    # could be a state abbreviation such as WA or CA).
    iso_alpha2 = set("""
        AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ
        CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR
        GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO
        JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ
        MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA
        RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO
        TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW
    """.split())
    country_name_markers = (
        "united states", "united kingdom", "canada", "germany", "france",
        "ireland", "netherlands", "poland", "singapore", "australia", "japan",
        "brazil", "mexico", "switzerland", "sweden", "spain", "portugal",
        "romania", "serbia", "israel", "united arab emirates", "taiwan", "chile",
        "argentina", "belgium", "south africa", "korea", "colombia", "hong kong",
        "türkiye", "turkey", "italy", "denmark", "costa rica", "philippines",
        "estonia", "norway", "finland", "austria", "czechia", "czech republic",
        "hungary", "greece", "indonesia", "malaysia", "thailand", "vietnam",
        "new zealand", "ukraine", "saudi arabia", "egypt", "kenya", "nigeria",
        "peru", "uruguay", "croatia", "slovenia", "slovakia", "bulgaria",
        "latvia", "lithuania", "luxembourg", "cyprus", "qatar", "kuwait",
        "bahrain", "oman", "nepal", "sri lanka", "bangladesh",
    )
    padded = f" {normalized} "
    if any(marker in padded for marker in country_name_markers):
        return False, "outside_india"

    for location in locations:
        pieces = [piece.strip().upper() for piece in re.split(r"[,;|]", location) if piece.strip()]
        if not pieces:
            continue
        for code in (pieces[0], pieces[-1]):
            if code == "IN":
                return True, "india_location"
            if len(code) == 2 and code in iso_alpha2 and code != "IN":
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
