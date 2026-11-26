from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


SOFTWARE_ROLE_RE = re.compile(
    r"\b(?:software engineer|software developer|software development engineer|software dev engineer|"
    r"software dev eng|sde ?[0-9]|sde|swe|back[ -]?end (?:engineer|developer)|front[ -]?end (?:engineer|developer)|"
    r"full[ -]?stack (?:engineer|developer)|platform engineer|site reliability engineer|\bsre\b|"
    r"software security engineer|test automation engineer|"
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

# Job titles that name a non-engineering ROLE. These always exclude, whatever else the title says.
_HARD_NON_SOFTWARE_RE = re.compile(
    r"\b(?:customer support|technical support|support associate|support analyst|"
    r"account executive|account manager|sales|business development|talent acquisition|"
    r"recruiter|human resources|\bhr\b|operations manager|"
    r"copywriter|designer|product manager|"
    r"program manager|project manager|customer success|technical account manager)\b",
    re.IGNORECASE,
)
# Business DOMAIN words. They name the team a software engineer works for ("Software Dev Engineer,
# Finance Technology", "SDE, Supply Chain Automation"), so they only exclude a title that is not
# clearly a software engineering title.
_SOFT_NON_SOFTWARE_RE = re.compile(r"\b(?:finance|accounting|warehouse|supply chain|marketing)\b", re.IGNORECASE)
_STRONG_SOFTWARE_TITLE_RE = re.compile(
    r"\b(?:software (?:dev(?:elopment)? )?(?:engineer|developer)|software engineer|sde ?[0-9]?|swe|"
    r"(?:back|front)[ -]?end (?:engineer|developer)|full[ -]?stack (?:engineer|developer))\b",
    re.IGNORECASE,
)


class _NonSoftwareMatcher:
    """Drop-in for the old NON_SOFTWARE_ROLE_RE (callers only use .search)."""

    @staticmethod
    def search(text: str):
        found = _HARD_NON_SOFTWARE_RE.search(text)
        if found:
            return found
        if _STRONG_SOFTWARE_TITLE_RE.search(text):
            return None
        return _SOFT_NON_SOFTWARE_RE.search(text)


NON_SOFTWARE_ROLE_RE = _NonSoftwareMatcher()

SENIORITY_TITLE_RE = re.compile(
    r"\b(?:senior|sr\.?|staff|principal|distinguished|fellow|lead|manager|"
    r"director|head|chief|architect|vice president|vp)\b|\b(?:engineer|developer|sde)\s*(?:iv|v|4|5)\b",
    re.IGNORECASE,
)
INTERN_TITLE_RE = re.compile(r"\b(?:intern|internship|apprentice|trainee)\b", re.IGNORECASE)

# Headings that are unmistakable wherever they appear.
_STRONG_MINIMUM_HEADING = (
    r"(?:(?:minimum|basic|required|mandatory)\s+qualifications|minimum\s+requirements|required\s+experience|"
    r"what\s+you(?:'|’)?ll\s+need|what\s+you\s+will\s+need)"
)
# A bare "requirements" is a heading only when it stands alone on its line or is followed by a colon. In a
# sentence ("non-functional requirements such as ...") it is an ordinary word.
_MINIMUM_SECTION_RE = re.compile(
    _STRONG_MINIMUM_HEADING + r"|^[ \t#*•\-]*(?:job\s+)?requirements\b[ \t]*(?::|\r?$)|\brequirements\s*:",
    re.IGNORECASE | re.MULTILINE,
)
_SECTION_END_RE = re.compile(
    r"(?:preferred qualifications|nice to have|preferred skills|bonus points|about the team|responsibilities|what you'll do|what you will do)",
    re.IGNORECASE,
)
_PHD_RE = re.compile(r"\b(?:ph\.?\s*d\.?|doctorate|doctoral degree)\b", re.IGNORECASE)

# A heading that starts a list of optional extras: it starts a line, or has a colon after it.
# "The preferred qualifications are a bonus" is a sentence, not a heading.
_PREFERRED_PHRASE = (
    r"(?:preferred\s+(?:qualifications|skills|experience|requirements)|nice[ -]to[ -]haves?|good[ -]to[ -]haves?|"
    r"bonus\s+(?:points|skills|qualifications))"
)
_PREFERRED_HEADING_RE = re.compile(
    r"^[ \t#*•\-]*" + _PREFERRED_PHRASE + r"(?![ \t]+(?:are|is|will)\b)[^\n.]{0,40}?(?::|\r?$)|" + _PREFERRED_PHRASE + r"\s*:",
    re.IGNORECASE | re.MULTILINE,
)
# Where an optional list stops.
_AFTER_PREFERRED_RE = re.compile(
    _STRONG_MINIMUM_HEADING + r"|^[ \t#*•\-]*(?:key\s+)?(?:job\s+)?(?:requirements|responsibilities)\b[^\n]{0,30}?(?::|\r?$)"
    r"|^[ \t]*(?-i:[A-Z])[A-Za-z /&]{2,30}:[ \t]*$",  # any other short "Something:" line starts a new part
    re.IGNORECASE | re.MULTILINE,
)

_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                 "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
_NUMBER = r"(?:\d{1,2}(?:\.\d+)?|" + "|".join(_NUMBER_WORDS) + r")"
# "3 years", "3+ yrs", "2–5 years", "7years+", "six (6) years", "6 months to 12 years".
_YEARS_RE = re.compile(
    r"(?<![\w.])(?P<low>" + _NUMBER + r")\s*(?:\(\s*\d+\s*\)\s*)?(?P<low_unit>months?\b\s*)?(?P<plus>\+|plus\b)?\s*"
    r"(?:(?:-|–|—|to\b)\s*" + _NUMBER + r"\s*\+?\s*)?(?:years?|yrs?)(?![a-z])(?P<tail_plus>\s*\+)?",
    re.IGNORECASE,
)
_NOT_EXPERIENCE_AFTER_RE = re.compile(
    r"^\W*(?:(?:full[ -]time\s+)?(?:degree|bachelor|college|university|diploma|program|undergraduate)|old\b|of age\b|ago\b|"
    r"bond\b|contract\b|warranty\b|anniversary\b|in a row\b|running\b)",
    re.IGNORECASE,
)
_NOT_EXPERIENCE_BEFORE_RE = re.compile(
    r"(?:\b(?:past|last|next|previous|first|every|within|since|founded)|\bfor (?:over|more than|nearly|almost|the past)|"
    r"\b(?:over|in) the)\s*$",
    re.IGNORECASE,
)
# The sentence is about the employer, not about you.
_EMPLOYER_SENTENCE_RE = re.compile(
    r"\b(?:we(?:'ve|’ve| have| bring)|(?:company|firm|platform|our team|our founders|our leadership) (?:has|have|with|brings)|"
    r"in business|combined experience|has been)\b|^\s*with (?:over|more than) ",
    re.IGNORECASE,
)
_EXPERIENCE_WORDS_RE = re.compile(
    r"experien|\b(?:building|developing|development|developer|programming|coding|engineering|engineer|working|designing|"
    r"hands[ -]on|professional|industry|relevant|software|shipping|expertise|role|position)\b",
    re.IGNORECASE,
)
_OPTIONAL_RE = re.compile(r"\b(?:preferred|a plus|nice to have|good to have|ideally|bonus|advantage(?:ous)?|desirable)\b", re.IGNORECASE)
_ADVANCED_DEGREE_RE = re.compile(r"^[^.;\n]{0,60}?\bwith (?:an? )?(?:advanced degree|master|ph\.?d)", re.IGNORECASE)


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


def _without_preferred(text: str) -> str:
    """The description with the "preferred / nice to have" lists cut out."""
    kept: list[str] = []
    position = 0
    while True:
        heading = _PREFERRED_HEADING_RE.search(text, position)
        if not heading:
            kept.append(text[position:])
            break
        kept.append(text[position:heading.start()])
        resume = _AFTER_PREFERRED_RE.search(text, heading.end())
        if not resume:
            break
        position = resume.start()
    return "\n".join(kept)


def extract_minimum_experience_years(description: str | None) -> float | None:
    """Extract the minimum experience a job description asks for.

    Optional ("preferred") lists are ignored. A range such as "2-5 years" counts as its lower end. When a
    description states several requirements ("3+ years of development, 2+ years of design"), all of them must
    be met, so the largest is returned. Returns None when no usable figure is stated.
    """
    text = _without_preferred(str(description or "").replace("\r", ""))
    found: list[tuple[float, bool]] = []  # (years, applies only with an advanced degree)
    for match in _YEARS_RE.finditer(text):
        raw = match.group("low").lower()
        years = float(_NUMBER_WORDS[raw]) if raw in _NUMBER_WORDS else float(raw)
        if match.group("low_unit"):
            years /= 12
        if years > 20:
            continue
        # The sentence or bullet around the figure.
        before = re.split(r"[.!?]\s|\n\s*[-•*]\s", text[max(0, match.start() - 90):match.start()])[-1]
        after_full = re.sub(r"\s+", " ", text[match.end():match.end() + 140]).strip()
        after = re.split(r"[.!?;](?:\s|$)| [•*] | - (?=\d)", after_full)[0][:110]
        before_flat = re.sub(r"\s+", " ", before)
        if _NOT_EXPERIENCE_AFTER_RE.search(after_full) or _NOT_EXPERIENCE_BEFORE_RE.search(before_flat):
            continue
        if _EMPLOYER_SENTENCE_RE.search(before_flat):
            continue
        if _OPTIONAL_RE.search(after[:90]) or _OPTIONAL_RE.search(before.split("\n")[-1]):
            continue
        more_than = before_flat.rstrip().endswith(">")  # "NodeJs ecosystem (>3 years)"
        stated_as_minimum = bool(more_than or match.group("plus") or match.group("tail_plus")
                                 or re.search(r"\b(?:at least|minimum(?: of)?|min\.?)\s*$", before_flat, re.IGNORECASE))
        about_experience = bool(_EXPERIENCE_WORDS_RE.search(after) or re.search(r"experien|expertise", before_flat[-60:], re.IGNORECASE))
        if not (about_experience or more_than or (stated_as_minimum and re.match(r"(?:of|in|with|as)\b", after, re.IGNORECASE))):
            continue
        found.append((years, bool(_ADVANCED_DEGREE_RE.search(after))))
    usable = [years for years, advanced in found if not advanced] or [years for years, _ in found]
    return round(max(usable), 2) if usable else None


def _clean_title(title: str | None) -> str:
    return re.sub(r"\s+", " ", str(title or "")).strip()


def is_non_software_title(title: str | None) -> bool:
    """True for support, sales, recruiting, finance and similar non-engineering titles."""
    return bool(NON_SOFTWARE_ROLE_RE.search(_clean_title(title)))


def matches_software_role_family(title: str | None) -> bool:
    """True when the title belongs to a target software-engineering family.

    This is only the role-family test (no seniority, experience or PhD checks)
    so callers that list every career level can reuse it.
    """
    clean = _clean_title(title)
    return bool(clean) and not NON_SOFTWARE_ROLE_RE.search(clean) and bool(SOFTWARE_ROLE_RE.search(clean))


def early_career_title_exclusion(title: str | None) -> str | None:
    """Return the reason an early-career search should drop this title, else None."""
    clean = _clean_title(title)
    if not clean:
        return "missing_title"
    if _PHD_RE.search(clean):
        return "phd_required_or_phd_targeted_title"
    if INTERN_TITLE_RE.search(clean):
        return "internship_or_trainee"
    if SENIORITY_TITLE_RE.search(clean):
        return "senior_or_lead_title"
    return None


def requires_phd(description: str | None) -> bool:
    """True when a PhD appears inside the minimum-qualifications section only.

    A PhD listed as "preferred" does not count as a mandatory requirement.
    """
    minimum_text, has_section = _minimum_qualification_text(description)
    return bool(has_section and _PHD_RE.search(minimum_text))


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

    # "Remote US", "Remote - USA", "Remote (UK)": the location itself names a foreign country, so
    # it is not open to India (found in a live sync: such jobs were held for review).
    foreign_remote = re.search(
        r"\b(?:us|usa|u s|u s a|uk|u k|emea|latam|latin america|south america|north america|europe|africa|middle east|eu)\b", re.sub(r"[^a-z0-9]+", " ", location_text.casefold())
    )
    if foreign_remote and not re.search(r"\b(india|worldwide|global)\b", normalized):
        return False, "outside_india"

    # "Remote - Worldwide" (how the remote boards write a job open to any country) is open to India.
    if not foreign_remote and re.search(r"\bremote\b", normalized) and re.search(r"\b(worldwide|global|anywhere)\b", normalized):
        return True, "remote_india_or_global_eligible"

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


ELIGIBLE = "eligible"
ELIGIBLE_NEEDS_REVIEW = "eligible_needs_review"
EXCLUDED = "excluded"
SOURCE_UNVERIFIED = "source_unverified"

_BROAD_TITLE_REVIEW_RE = re.compile(
    r"\b(?:application engineer|cloud engineer|cloud ai engineer|data and ai engineer|"
    r"salesforce application engineer|solutions engineer)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EligibilityDecision:
    """Explainable outcome of the deterministic eligibility layer.

    ``status`` is one of eligible / eligible_needs_review / excluded /
    source_unverified. ``reasons`` explains an exclusion; ``flags`` lists the
    reasons a job needs human review. Deterministic rules are authoritative;
    nothing here depends on an LLM.
    """

    status: str
    role_ok: bool
    role_reason: str
    location_ok: bool
    location_reason: str
    minimum_years: float | None
    flags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def reasons(self) -> tuple[str, ...]:
        reasons: list[str] = []
        if not self.role_ok:
            reasons.append(self.role_reason)
        if not self.location_ok:
            reasons.append(self.location_reason)
        return tuple(reasons)

    @property
    def passes_filters(self) -> bool:
        return self.role_ok and self.location_ok


def evaluate_eligibility(
    job: dict[str, Any],
    *,
    source_verified: bool = True,
    maximum_required_years: float = 2.0,
) -> EligibilityDecision:
    """Classify one job from title, description and location.

    - excluded: fails the role/experience/PhD or the India/remote rule.
    - eligible_needs_review: passes, but something is ambiguous (experience not
      stated, remote country unverified, missing description, broad title).
    - source_unverified: passes, but its source mapping is not verified/active,
      so it must not enter automatic sync.
    - eligible: passes with no review flags from a verified source.
    Undisclosed salary is never a reason to exclude.
    """
    title = str(job.get("title") or "").strip()
    description = str(job.get("description") or "")
    minimum_years = extract_minimum_experience_years(description)
    role_ok, role_reason = is_target_software_role(
        title, description, maximum_required_years=maximum_required_years
    )
    location_ok, location_reason = is_india_or_remote_eligible(job)

    flags: list[str] = []
    if not description.strip():
        flags.append("description_missing")
    if minimum_years is None:
        flags.append("minimum_experience_not_found_review")
    if location_reason == "remote_country_eligibility_unverified":
        flags.append("remote_country_eligibility_unverified")
    if _BROAD_TITLE_REVIEW_RE.search(title):
        flags.append("broad_title_manual_review")

    passes = role_ok and location_ok
    if not passes:
        status = EXCLUDED
    elif not source_verified:
        status = SOURCE_UNVERIFIED
        flags.append("source_mapping_unverified_review")
    elif flags:
        status = ELIGIBLE_NEEDS_REVIEW
    else:
        status = ELIGIBLE

    return EligibilityDecision(
        status=status,
        role_ok=role_ok,
        role_reason=role_reason,
        location_ok=location_ok,
        location_reason=location_reason,
        minimum_years=minimum_years,
        flags=tuple(flags),
    )
