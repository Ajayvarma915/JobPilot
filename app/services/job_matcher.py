from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from app.profile.candidate_profile import CandidateProfile
from app.services.job_normalizer import NormalizedJob


@dataclass(frozen=True)
class JobMatchResult:
    """
    Explainable candidate-to-job matching result.
    """

    score: float

    role_score: float
    seniority_score: float
    experience_score: float
    skills_score: float
    education_score: float
    location_score: float

    matched_skills: tuple[str, ...]
    required_years: float | None
    required_degree: str | None

    recommendation: str

    reasons: tuple[str, ...]
    concerns: tuple[str, ...]


ROLE_SCORES = {
    "software_engineering": 25.0,
    "frontend": 25.0,
    "full_stack": 25.0,
    "backend": 25.0,
    "cloud_devops": 18.0,
    "systems": 18.0,
    "security": 18.0,
    "data": 15.0,
    "ai_ml": 15.0,
    "engineering_other": 10.0,
    "internship": 8.0,
    "other": 5.0,
    "management": 0.0,
    "product": 0.0,
    "program_management": 0.0,
}


SENIORITY_SCORES = {
    "entry": 20.0,
    "mid": 16.0,
    "intern": 6.0,
    "senior": 6.0,
    "staff": 2.0,
    "manager": 0.0,
    "executive": 0.0,
    "unknown": 8.0,
}


SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    "Java": (
        "java",
    ),
    "Python": (
        "python",
    ),
    "JavaScript": (
        "javascript",
        "js",
    ),
    "React.js": (
        "react.js",
        "react",
    ),
    "Next.js": (
        "next.js",
        "nextjs",
        "next js",
    ),
    "Tailwind CSS": (
        "tailwind css",
        "tailwindcss",
    ),
    "HTML": (
        "html",
    ),
    "CSS": (
        "css",
    ),
    "Git": (
        "git",
    ),
    "GitHub": (
        "github",
    ),
    "Firebase": (
        "firebase",
    ),
    "Chart.js": (
        "chart.js",
        "chartjs",
    ),
    "Auth.js": (
        "auth.js",
        "authjs",
    ),
    "PyWhatKit": (
        "pywhatkit",
    ),
    "NLP": (
        "nlp",
        "natural language processing",
    ),
    "Machine Learning": (
        "machine learning",
    ),
    "Data Structures and Algorithms": (
        "data structures",
        "algorithms",
        "data structures and algorithms",
    ),
    "Object Oriented Programming": (
        "object oriented programming",
        "object-oriented programming",
        "oops",
    ),
}


def _job_value(
    job: NormalizedJob | Mapping[str, Any] | Any,
    field: str,
    default: Any = None,
) -> Any:
    if isinstance(job, Mapping):
        return job.get(field, default)

    return getattr(
        job,
        field,
        default,
    )


def _minimum_qualification_section(
    description: str,
) -> str:
    """
    Extract only the Minimum Qualifications portion.

    Preferred Qualifications often contain softer requirements,
    so they should not be treated as hard minimum requirements.
    """

    if not description:
        return ""

    normalized = description.replace(
        "\r\n",
        "\n",
    )

    match = re.search(
        r"minimum\s+qualifications"
        r"(.*?)(?="
        r"\n\s*preferred\s+qualifications"
        r"|\n\s*responsibilities"
        r"|$)",
        normalized,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if match is not None:
        return match.group(1).strip()

    return normalized


def _extract_required_years(
    description: str,
) -> float | None:
    """
    Extract an explicit experience requirement from Minimum
    Qualifications.

    We use the largest explicit requirement because a job can
    contain multiple requirements such as:

        3 years software development
        2 years system design
    """

    minimum_section = _minimum_qualification_section(
        description
    )

    matches = re.findall(
        r"(\d+(?:\.\d+)?)\s*\+?\s+years?\s+of\s+experience",
        minimum_section,
        flags=re.IGNORECASE,
    )

    if not matches:
        return None

    values = [
        float(value)
        for value in matches
    ]

    return max(values)


def _extract_required_degree(
    description: str,
) -> str | None:
    """
    Detect the highest explicit degree requirement from
    Minimum Qualifications.
    """

    minimum_section = _minimum_qualification_section(
        description
    ).lower()

    if re.search(
        r"\bph\.?\s*d\.?\b|\bphd\b",
        minimum_section,
    ):
        return "phd"

    if re.search(
        r"\bmaster'?s?\b|\bms\b|\bm\.s\.\b",
        minimum_section,
    ):
        return "masters"

    if re.search(
        r"\bbachelor'?s?\b|\bbs\b|\bb\.s\.\b"
        r"|\bbtech\b|\bb\.tech\b",
        minimum_section,
    ):
        return "bachelors"

    return None


def _skill_in_text(
    aliases: tuple[str, ...],
    text: str,
) -> bool:
    normalized_text = text.lower()

    for alias in aliases:
        alias_lower = alias.lower()

        escaped = re.escape(
            alias_lower
        )

        # Handle normal word boundaries for simple terms.
        if re.search(
            rf"(?<!\w){escaped}(?!\w)",
            normalized_text,
        ):
            return True

    return False


def _find_matched_skills(
    candidate: CandidateProfile,
    title: str,
    description: str,
) -> tuple[str, ...]:
    """
    Determine which candidate skills are actually mentioned
    in the job title or JD.
    """

    text = (
        f"{title}\n"
        f"{description}"
    ).lower()

    matched: list[str] = []

    for skill in candidate.technical_skills:
        aliases = SKILL_ALIASES.get(
            skill,
            (skill,),
        )

        if _skill_in_text(
            aliases,
            text,
        ):
            matched.append(skill)

    return tuple(matched)


def _score_skills(
    matched_skills: tuple[str, ...],
) -> float:
    """
    Convert the number of matched candidate skills to /20.

    The score is capped so that having many common keywords
    cannot overwhelm role/seniority suitability.
    """

    count = len(matched_skills)

    if count <= 0:
        return 0.0

    return min(
        20.0,
        count / 6.0 * 20.0,
    )


def _score_experience(
    normalized_job: NormalizedJob,
    required_years: float | None,
    candidate_years: float,
) -> float:
    """
    Score explicit experience requirements.

    A job without a stated minimum receives a score based on
    the normalized seniority.

    A job with an explicit requirement compares it against the
    candidate's years of experience.
    """

    if required_years is None:
        if normalized_job.normalized_experience == "entry":
            return 20.0

        if normalized_job.normalized_experience == "intern":
            return 12.0

        if normalized_job.normalized_experience == "mid":
            return 10.0

        if normalized_job.normalized_experience == "senior":
            return 5.0

        if normalized_job.normalized_experience == "staff":
            return 2.0

        return 5.0

    if required_years <= 0:
        return 20.0

    if candidate_years >= required_years:
        return 20.0

    if candidate_years <= 0:
        # No professional experience is currently represented
        # in the candidate profile.
        return 0.0

    ratio = candidate_years / required_years

    return min(
        20.0,
        ratio * 20.0,
    )


def _score_education(
    required_degree: str | None,
    candidate: CandidateProfile,
) -> float:
    """
    Score the candidate against the minimum degree requirement.
    """

    candidate_degrees = {
        value.lower()
        for value in candidate.degrees
    }

    if required_degree is None:
        return 8.0

    if required_degree == "bachelors":
        if "btech" in candidate_degrees:
            return 10.0

        if "bachelor" in candidate_degrees:
            return 10.0

        return 5.0

    if required_degree == "masters":
        if "masters" in candidate_degrees:
            return 10.0

        return 4.0

    if required_degree == "phd":
        return 0.0

    return 5.0


def _score_location(
    normalized_job: NormalizedJob,
    candidate: CandidateProfile,
) -> float:
    """
    Score location compatibility.
    """

    candidate_locations = {
        value.lower()
        for value in candidate.target_locations
    }

    job_locations = {
        value.lower()
        for value in normalized_job.locations
    }

    if (
        candidate_locations
        & job_locations
    ):
        return 5.0

    return 0.0


def _build_reasons(
    normalized_job: NormalizedJob,
    matched_skills: tuple[str, ...],
    candidate: CandidateProfile,
    role_score: float,
    seniority_score: float,
    required_years: float | None,
    required_degree: str | None,
) -> list[str]:

    reasons: list[str] = []

    if normalized_job.role_family in (
        "software_engineering",
        "frontend",
        "full_stack",
        "backend",
    ):
        reasons.append(
            "Role family matches the candidate's target software-engineering roles."
        )

    elif normalized_job.role_family in (
        "cloud_devops",
        "systems",
        "security",
        "data",
        "ai_ml",
    ):
        reasons.append(
            "Role is technically related to the candidate's software-engineering target."
        )

    if normalized_job.normalized_experience in (
        "entry",
        "mid",
    ):
        reasons.append(
            f"Normalized seniority is {normalized_job.normalized_experience}, "
            "which is within the candidate's target range."
        )

    if matched_skills:
        reasons.append(
            "Matched skills: "
            + ", ".join(matched_skills)
            + "."
        )

    if normalized_job.locations:
        candidate_location_set = {
            value.lower()
            for value in candidate.target_locations
        }

        job_location_set = {
            value.lower()
            for value in normalized_job.locations
        }

        if candidate_location_set & job_location_set:
            reasons.append(
                "Job location matches a target location."
            )

    if required_years is None:
        reasons.append(
            "No explicit minimum years-of-experience requirement "
            "was detected."
        )
    else:
        reasons.append(
            f"Minimum qualification mentions "
            f"{required_years:g} year(s) of experience."
        )

    if required_degree == "bachelors":
        reasons.append(
            "Minimum qualification requires a bachelor's-level degree."
        )

    if role_score == 0:
        reasons.append(
            "Role family is outside the candidate's target role families."
        )

    if seniority_score == 0:
        reasons.append(
            "Job seniority is outside the candidate's target range."
        )

    return reasons


def _build_concerns(
    normalized_job: NormalizedJob,
    candidate: CandidateProfile,
    required_years: float | None,
    required_degree: str | None,
    matched_skills: tuple[str, ...],
) -> list[str]:

    concerns: list[str] = []

    if normalized_job.is_management_role:
        concerns.append(
            "This is a management/product/program-management role."
        )

    if normalized_job.normalized_experience in (
        "senior",
        "staff",
        "manager",
        "executive",
    ):
        concerns.append(
            f"Normalized seniority is "
            f"{normalized_job.normalized_experience}."
        )

    if required_years is not None:
        if candidate.years_of_experience < required_years:
            concerns.append(
                f"Candidate profile has "
                f"{candidate.years_of_experience:g} years of experience, "
                f"while the JD requires "
                f"{required_years:g} year(s)."
            )

    if required_degree == "masters":
        concerns.append(
            "The JD minimum qualification mentions a master's degree."
        )

    elif required_degree == "phd":
        concerns.append(
            "The JD minimum qualification requires a PhD."
        )

    if not matched_skills:
        concerns.append(
            "No direct candidate-skill matches were detected."
        )

    elif len(matched_skills) <= 2:
        concerns.append(
            "Only a small number of candidate skills matched the JD."
        )

    return concerns


def _recommendation(
    score: float,
) -> str:

    if score >= 75:
        return "strong_match"

    if score >= 60:
        return "good_match"

    if score >= 45:
        return "review"

    return "low_match"


def match_job(
    job: NormalizedJob | Mapping[str, Any] | Any,
    candidate: CandidateProfile,
    description: str | None = None,
) -> JobMatchResult:
    """
    Score one normalized job against a candidate profile.

    The function can accept:
    - a NormalizedJob object
    - a SQLAlchemy Job object
    - a mapping containing normalized fields

    For SQLAlchemy/raw jobs, the description must be supplied
    separately when available.
    """

    title = str(
        _job_value(
            job,
            "title",
            "",
        )
        or ""
    )

    if description is None:
        description = str(
            _job_value(
                job,
                "description",
                "",
            )
            or ""
        )

    role_family = str(
        _job_value(
            job,
            "role_family",
            "other",
        )
    )

    normalized_experience = str(
        _job_value(
            job,
            "normalized_experience",
            "unknown",
        )
    )

    locations = tuple(
        _job_value(
            job,
            "locations",
            (),
        )
        or ()
    )

    normalized_job = (
        job
        if isinstance(job, NormalizedJob)
        else NormalizedJob(
            external_id=None,
            title=title,
            normalized_title=title.lower(),
            role_family=role_family,
            normalized_experience=normalized_experience,
            source_experience_level=None,
            locations=locations,
            employment_type="unknown",
            technologies=(),
            is_engineering_role=(
                role_family
                not in {
                    "management",
                    "product",
                    "program_management",
                }
            ),
            is_management_role=(
                role_family
                in {
                    "management",
                    "product",
                    "program_management",
                }
            ),
        )
    )

    role_score = ROLE_SCORES.get(
        normalized_job.role_family,
        5.0,
    )

    seniority_score = SENIORITY_SCORES.get(
        normalized_job.normalized_experience,
        8.0,
    )

    required_years = _extract_required_years(
        description
    )

    required_degree = _extract_required_degree(
        description
    )

    experience_score = _score_experience(
        normalized_job=normalized_job,
        required_years=required_years,
        candidate_years=candidate.years_of_experience,
    )

    matched_skills = _find_matched_skills(
        candidate=candidate,
        title=title,
        description=description,
    )

    skills_score = _score_skills(
        matched_skills
    )

    education_score = _score_education(
        required_degree=required_degree,
        candidate=candidate,
    )

    location_score = _score_location(
        normalized_job=normalized_job,
        candidate=candidate,
    )

    raw_score = (
        role_score
        + seniority_score
        + experience_score
        + skills_score
        + education_score
        + location_score
    )

    final_score = min(
        100.0,
        raw_score,
    )

    # Strongly penalize jobs with explicit qualification
    # requirements that the candidate profile cannot satisfy.
    if (
        required_degree == "phd"
    ):
        final_score = min(
            final_score,
            35.0,
        )

    elif (
        required_degree == "masters"
    ):
        final_score = min(
            final_score,
            59.0,
        )

    if (
        required_years is not None
        and candidate.years_of_experience < required_years
    ):
        final_score = min(
            final_score,
            69.0,
        )

    reasons = _build_reasons(
        normalized_job=normalized_job,
        matched_skills=matched_skills,
        candidate=candidate,
        role_score=role_score,
        seniority_score=seniority_score,
        required_years=required_years,
        required_degree=required_degree,
    )

    concerns = _build_concerns(
        normalized_job=normalized_job,
        candidate=candidate,
        required_years=required_years,
        required_degree=required_degree,
        matched_skills=matched_skills,
    )

    return JobMatchResult(
        score=round(
            final_score,
            2,
        ),
        role_score=round(
            role_score,
            2,
        ),
        seniority_score=round(
            seniority_score,
            2,
        ),
        experience_score=round(
            experience_score,
            2,
        ),
        skills_score=round(
            skills_score,
            2,
        ),
        education_score=round(
            education_score,
            2,
        ),
        location_score=round(
            location_score,
            2,
        ),
        matched_skills=matched_skills,
        required_years=required_years,
        required_degree=required_degree,
        recommendation=_recommendation(
            final_score
        ),
        reasons=tuple(reasons),
        concerns=tuple(concerns),
    )