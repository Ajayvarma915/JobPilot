from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class NormalizedJob:
    """
    Normalized representation of a raw job.

    Raw source values remain untouched in the database.
    """

    external_id: str | None
    title: str
    normalized_title: str
    role_family: str
    normalized_experience: str
    source_experience_level: str | None
    locations: tuple[str, ...]
    employment_type: str
    technologies: tuple[str, ...]
    is_engineering_role: bool
    is_management_role: bool


TECHNOLOGY_PATTERNS: tuple[tuple[str, str], ...] = (
    ("C++", r"\bc\+\+\b"),
    ("C#", r"\bc#\b"),
    ("Python", r"\bpython\b"),
    ("Java", r"\bjava\b"),
    ("JavaScript", r"\bjavascript\b"),
    ("TypeScript", r"\btypescript\b"),
    ("React", r"\breact(?:\.js)?\b"),
    ("Next.js", r"\bnext(?:\.js)?\b"),
    ("Node.js", r"\bnode(?:\.js)?\b"),
    (".NET", r"(?<!\w)\.net\b"),
    ("ASP.NET", r"\basp\.net\b"),
    ("Go", r"\bgolang\b"),
    ("Ruby", r"\bruby\b"),
    ("PHP", r"\bphp\b"),
    ("Kotlin", r"\bkotlin\b"),
    ("Swift", r"\bswift\b"),
    ("SQL", r"\bsql\b"),
    ("PostgreSQL", r"\bpostgres(?:ql)?\b"),
    ("MySQL", r"\bmysql\b"),
    ("MongoDB", r"\bmongodb\b"),
    ("Redis", r"\bredis\b"),
    ("Kafka", r"\bkafka\b"),
    ("Docker", r"\bdocker\b"),
    ("Kubernetes", r"\bkubernetes\b"),
    ("Terraform", r"\bterraform\b"),
    ("AWS", r"\baws\b|amazon web services"),
    ("Azure", r"\bazure\b"),
    ("Google Cloud", r"\bgoogle cloud\b|\bgcp\b"),
    ("Linux", r"\blinux\b"),
    ("Git", r"\bgit\b"),
    ("FastAPI", r"\bfastapi\b"),
    ("Django", r"\bdjango\b"),
    ("Spring", r"\bspring(?: boot)?\b"),
    ("LangChain", r"\blangchain\b"),
    ("LangGraph", r"\blanggraph\b"),
    ("LLM", r"\bllm(?:s)?\b|large language model"),
    ("RAG", r"\brag\b|\bretrieval augmented generation\b"),
    ("Machine Learning", r"\bmachine learning\b"),
    ("Artificial Intelligence", r"\bartificial intelligence\b"),
)


def _get_value(
    job: Mapping[str, Any] | Any,
    field_name: str,
    default: Any = None,
) -> Any:
    """
    Read a field from either a mapping or a SQLAlchemy model.
    """

    if isinstance(job, Mapping):
        return job.get(field_name, default)

    return getattr(
        job,
        field_name,
        default,
    )


def _clean_whitespace(value: str) -> str:
    return " ".join(value.split()).strip()


def _normalize_title(title: str) -> str:
    """
    Normalize title for matching while preserving meaning.
    """

    cleaned = _clean_whitespace(title)

    cleaned = cleaned.replace("–", "-")
    cleaned = cleaned.replace("—", "-")

    return cleaned.lower()


def _normalize_locations(
    location: Any,
) -> tuple[str, ...]:
    """
    Convert location values into a consistent tuple.
    """

    if location is None:
        return ()

    if isinstance(location, (list, tuple, set)):
        raw_locations = list(location)
    else:
        raw_locations = str(location).split(";")

    cleaned_locations: list[str] = []

    for item in raw_locations:
        value = _clean_whitespace(str(item))

        if value and value not in cleaned_locations:
            cleaned_locations.append(value)

    return tuple(cleaned_locations)


def _normalize_source_experience(
    value: Any,
) -> str | None:
    if value is None:
        return None

    cleaned = _clean_whitespace(str(value))

    if not cleaned:
        return None

    return cleaned


def _infer_experience(
    title: str,
    description: str,
    source_experience: str | None,
) -> str:
    """
    Infer normalized seniority.

    Title-specific signals take priority over the source's
    taxonomy because different companies use different levels.
    """

    title_lower = title.lower()

    # Internship must be checked first.
    if re.search(
        r"\bintern(?:ship)?\b",
        title_lower,
    ):
        return "intern"

    # Executive signals.
    if re.search(
        r"\bvice president\b|\bvp\b|\bchief\b|\bdirector\b",
        title_lower,
    ):
        return "executive"

    if re.search(
        r"\bhead of\b",
        title_lower,
    ):
        return "executive"

    # Management.
    if re.search(
        r"\bmanager\b|\bmanagement\b",
        title_lower,
    ):
        return "manager"

    # Staff / principal hierarchy.
    if re.search(
        r"\bprincipal\b|\bstaff\b|\bdistinguished\b",
        title_lower,
    ):
        return "staff"

    # Senior / lead hierarchy.
    if re.search(
        r"\bsenior\b|\bsr\.?\b|\blead\b",
        title_lower,
    ):
        return "senior"

    # Junior / entry-level hierarchy.
    if re.search(
        r"\bjunior\b|\bjr\.?\b|\bentry[- ]level\b",
        title_lower,
    ):
        return "entry"

    if re.search(
        r"\bengineer\s+i\b",
        title_lower,
    ):
        return "entry"

    # Roman numerals are company-dependent.
    if re.search(
        r"\bengineer\s+(ii|iii|iv|v)\b",
        title_lower,
    ):
        source = (
            source_experience or ""
        ).lower()

        if "early" in source or "entry" in source:
            return "entry"

        if "advanced" in source:
            return "senior"

        if "mid" in source:
            return "mid"

    # Description fallback.
    description_lower = description.lower()

    if re.search(
        r"\binternship\b|\bsummer intern\b",
        description_lower,
    ):
        return "intern"

    source = (
        source_experience or ""
    ).lower()

    source_mapping = {
        "early": "entry",
        "entry": "entry",
        "mid": "mid",
        "advanced": "senior",
        "senior": "senior",
        "staff": "staff",
        "principal": "staff",
        "manager": "manager",
        "intern": "intern",
        "internship": "intern",
    }

    if source in source_mapping:
        return source_mapping[source]

    return "unknown"


def _infer_role_family(
    title: str,
) -> str:
    """
    Assign a broad role family.

    Internships are detected before management/product categories
    so titles such as "Software Engineering PhD Intern" are not
    classified as "other".
    """

    title_lower = title.lower()

    # ---------------------------------------------------------
    # Internship
    # ---------------------------------------------------------

    if re.search(
        r"\bintern\b|\binternship\b",
        title_lower,
    ):
        return "internship"

    # ---------------------------------------------------------
    # Product / program / management
    # ---------------------------------------------------------

    if re.search(
        r"\bproduct manager\b|\bproduct management\b",
        title_lower,
    ):
        return "product"

    if re.search(
        r"\btechnical program manager\b"
        r"|\bprogram manager\b"
        r"|\btechnical program management\b",
        title_lower,
    ):
        return "program_management"

    if re.search(
        r"\bmanager\b|\bmanagement\b"
        r"|\bdirector\b|\bhead of\b",
        title_lower,
    ):
        return "management"

    # ---------------------------------------------------------
    # AI / ML
    # ---------------------------------------------------------

    if re.search(
        r"\bai/ml\b"
        r"|\bmachine learning\b"
        r"|\bartificial intelligence\b"
        r"|\bdeep learning\b",
        title_lower,
    ):
        return "ai_ml"

    # "AI" as a standalone title word is useful, but avoid
    # making a generic engineering title AI/ML merely because
    # the source mentions AI elsewhere in the title.
    if re.search(
        r"(?<![a-z])ai(?![a-z])",
        title_lower,
    ):
        return "ai_ml"

    # ---------------------------------------------------------
    # Security
    # ---------------------------------------------------------

    if re.search(
        r"\bsecurity\b|\bprivacy\b"
        r"|\bcybersecurity\b|\bcyber security\b",
        title_lower,
    ):
        return "security"

    # ---------------------------------------------------------
    # Data
    # ---------------------------------------------------------

    if re.search(
        r"\bdata engineer\b"
        r"|\bdata engineering\b"
        r"|\bdata scientist\b"
        r"|\bdata science\b"
        r"|\banalytics engineer\b",
        title_lower,
    ):
        return "data"

    # ---------------------------------------------------------
    # Frontend
    # ---------------------------------------------------------

    if re.search(
        r"\bfront[- ]end\b"
        r"|\bfrontend\b"
        r"|\bui engineer\b",
        title_lower,
    ):
        return "frontend"

    # ---------------------------------------------------------
    # Backend
    # ---------------------------------------------------------

    if re.search(
        r"\bback[- ]end\b|\bbackend\b",
        title_lower,
    ):
        return "backend"

    # ---------------------------------------------------------
    # Full stack
    # ---------------------------------------------------------

    if re.search(
        r"\bfull[- ]stack\b|\bfullstack\b",
        title_lower,
    ):
        return "full_stack"

    # ---------------------------------------------------------
    # Cloud / DevOps / Infrastructure
    # ---------------------------------------------------------

    if re.search(
        r"\bcloud\b"
        r"|\binfrastructure\b"
        r"|\bdevops\b"
        r"|\bplatform engineer\b"
        r"|\bsite reliability\b"
        r"|\bsre\b"
        r"|\bdeployment\b"
        r"|\bproduction engineering\b",
        title_lower,
    ):
        return "cloud_devops"

    # ---------------------------------------------------------
    # Systems
    # ---------------------------------------------------------

    if re.search(
        r"\bsystems?\b|\bsystem development\b",
        title_lower,
    ):
        return "systems"

    # ---------------------------------------------------------
    # General software engineering
    # ---------------------------------------------------------

    if re.search(
        r"\bsoftware engineer\b"
        r"|\bsoftware developer\b"
        r"|\bapplication engineer\b"
        r"|\bdeveloper\b",
        title_lower,
    ):
        return "software_engineering"

    # ---------------------------------------------------------
    # Other engineering
    # ---------------------------------------------------------

    if re.search(
        r"\bengineer\b",
        title_lower,
    ):
        return "engineering_other"

    return "other"


def _infer_employment_type(
    title: str,
    description: str,
    source_value: str | None,
) -> str:
    """
    Infer employment type conservatively.
    """

    combined = (
        f"{title} "
        f"{description} "
        f"{source_value or ''}"
    ).lower()

    if re.search(
        r"\bintern\b|\binternship\b",
        combined,
    ):
        return "internship"

    if re.search(
        r"\bpart[- ]time\b",
        combined,
    ):
        return "part_time"

    if re.search(
        r"\bcontract(?:or)?\b",
        combined,
    ):
        return "contract"

    if re.search(
        r"\bfull[- ]time\b",
        combined,
    ):
        return "full_time"

    return "unknown"


def _extract_technologies(
    title: str,
    description: str,
) -> tuple[str, ...]:
    """
    Extract known technology keywords.

    This is deliberately deterministic keyword extraction.
    """

    combined = (
        f"{title}\n{description}"
    ).lower()

    found: list[str] = []

    for label, pattern in TECHNOLOGY_PATTERNS:
        if re.search(
            pattern,
            combined,
            flags=re.IGNORECASE,
        ):
            found.append(label)

    return tuple(found)


def normalize_job(
    job: Mapping[str, Any] | Any,
) -> NormalizedJob:
    """
    Normalize a raw job mapping or SQLAlchemy Job object.
    """

    external_id = _get_value(
        job,
        "external_id",
    )

    title = _clean_whitespace(
        str(
            _get_value(
                job,
                "title",
                "",
            )
            or ""
        )
    )

    description = _clean_whitespace(
        str(
            _get_value(
                job,
                "description",
                "",
            )
            or ""
        )
    )

    source_experience = (
        _normalize_source_experience(
            _get_value(
                job,
                "experience_level",
            )
        )
    )

    role_family = _infer_role_family(
        title
    )

    normalized_experience = _infer_experience(
        title=title,
        description=description,
        source_experience=source_experience,
    )

    locations = _normalize_locations(
        _get_value(
            job,
            "location",
        )
    )

    employment_type = _infer_employment_type(
        title=title,
        description=description,
        source_value=_get_value(
            job,
            "employment_type",
        ),
    )

    technologies = _extract_technologies(
        title=title,
        description=description,
    )

    is_management_role = role_family in {
        "management",
        "program_management",
        "product",
    }

    # Management/product/program positions are not considered
    # candidate-target engineering roles even when the title
    # contains the word "engineer".
    is_engineering_role = (
        not is_management_role
        and role_family in {
            "software_engineering",
            "frontend",
            "backend",
            "full_stack",
            "cloud_devops",
            "systems",
            "security",
            "data",
            "ai_ml",
            "engineering_other",
        }
    )

    return NormalizedJob(
        external_id=(
            str(external_id)
            if external_id is not None
            else None
        ),
        title=title,
        normalized_title=_normalize_title(
            title
        ),
        role_family=role_family,
        normalized_experience=(
            normalized_experience
        ),
        source_experience_level=(
            source_experience
        ),
        locations=locations,
        employment_type=employment_type,
        technologies=technologies,
        is_engineering_role=(
            is_engineering_role
        ),
        is_management_role=(
            is_management_role
        ),
    )