from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass(slots=True)
class ResumeContact:
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin: str | None = None
    github: str | None = None
    location: str | None = None


@dataclass(slots=True)
class ResumeEducation:
    degree: str | None = None
    field_of_study: str | None = None
    institution: str | None = None
    cgpa: float | None = None
    start_date: str | None = None
    end_date: str | None = None
    location: str | None = None
    raw_text: str = ""


@dataclass(slots=True)
class ResumeProject:
    name: str
    description: str = ""
    technologies: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ResumeExperience:
    company: str | None = None
    role: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    location: str | None = None
    bullets: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ResumeCertification:
    name: str
    issuer: str | None = None


@dataclass(slots=True)
class ParsedResume:
    raw_text: str
    contact: ResumeContact
    skills: list[str] = field(default_factory=list)
    programming_languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)
    education: list[ResumeEducation] = field(default_factory=list)
    projects: list[ResumeProject] = field(default_factory=list)
    experience: list[ResumeExperience] = field(default_factory=list)
    certifications: list[ResumeCertification] = field(default_factory=list)
    achievements: list[str] = field(default_factory=list)
    sections: dict[str, list[str]] = field(default_factory=dict)


# Alias values normalize spelling variants into a single canonical skill.
TECHNOLOGY_ALIASES: dict[str, tuple[str, ...]] = {
    "Data Structures and Algorithms": ("Data Structures and Algorithms", "DSA"),
    "Object-Oriented Programming": (
        "Object Oriented Programming",
        "Object-Oriented Programming",
        "OOPS",
        "OOP",
    ),
    "JavaScript": ("JavaScript", "JS"),
    "TypeScript": ("TypeScript", "TS"),
    "Python": ("Python",),
    "Java": ("Java",),
    "C++": ("C++", "Cpp"),
    "C#": ("C#", "C Sharp"),
    "SQL": ("SQL",),
    "HTML": ("HTML",),
    "CSS": ("CSS",),
    "React.js": ("React.js", "ReactJS", "React"),
    "Tailwind CSS": ("Tailwind CSS", "Tailwind"),
    "Next.js": ("Next.js", "NextJS"),
    "Node.js": ("Node.js", "NodeJS"),
    "Express.js": ("Express.js", "ExpressJS"),
    "Auth.js": ("Auth.js", "AuthJS"),
    "Chart.js": ("Chart.js", "ChartJS"),
    "GitHub": ("GitHub", "Git Hub"),
    "Git": ("Git",),
    "Firebase": ("Firebase",),
    "PyWhatKit": ("PyWhatKit", "Py WhatKit"),
    "AWS": ("AWS", "Amazon Web Services"),
    "Microsoft Azure": ("Microsoft Azure", "Azure"),
    "Docker": ("Docker",),
    "Kubernetes": ("Kubernetes",),
    "FastAPI": ("FastAPI",),
    "Flask": ("Flask",),
    "Django": ("Django",),
    ".NET": (".NET", "Dotnet"),
    "Machine Learning": ("Machine Learning", "ML"),
    "Natural Language Processing": ("Natural Language Processing", "NLP"),
    "CRUD": ("CRUD",),
    "Authentication": ("Authentication", "AuthN"),
    "Session Management": ("Session Management",),
    "API": ("API", "APIs"),
}

PROGRAMMING_LANGUAGES = {
    "Java",
    "Python",
    "JavaScript",
    "TypeScript",
    "C++",
    "C#",
    "SQL",
}

FRAMEWORKS = {
    "React.js",
    "Tailwind CSS",
    "Next.js",
    "Node.js",
    "Express.js",
    "Auth.js",
    "FastAPI",
    "Flask",
    "Django",
    ".NET",
}

TOOLS = {
    "Git",
    "GitHub",
    "Chart.js",
    "Firebase",
    "PyWhatKit",
    "AWS",
    "Microsoft Azure",
    "Docker",
    "Kubernetes",
}

CONCEPTS = {
    "Data Structures and Algorithms",
    "Object-Oriented Programming",
    "Machine Learning",
    "Natural Language Processing",
    "CRUD",
    "Authentication",
    "Session Management",
    "API",
}

SECTION_ALIASES: dict[str, set[str]] = {
    "education": {"EDUCATION", "ACADEMIC BACKGROUND"},
    "skills": {"SKILLS", "TECHNICAL SKILLS", "TECHNICAL SUMMARY"},
    "projects": {"PROJECTS", "PERSONAL PROJECTS", "ACADEMIC PROJECTS"},
    "experience": {
        "EXPERIENCE",
        "WORK EXPERIENCE",
        "PROFESSIONAL EXPERIENCE",
        "VIRTUAL INTERNSHIP",
        "INTERNSHIP",
        "INTERNSHIPS",
    },
    "certifications": {"CERTIFICATES", "CERTIFICATIONS", "CERTIFICATION"},
    "achievements": {
        "ACHIEVEMENTS",
        "AWARDS AND ACHIEVEMENTS",
        "AWARDS",
    },
    "summary": {
        "SUMMARY",
        "PROFILE",
        "OBJECTIVE",
        "PROFESSIONAL SUMMARY",
    },
}

BULLET_PREFIX_RE = re.compile(
    r"^\s*(?:(?:\d+\s*[.)])\s*)?(?:[•●▪◦*\-–—]\s*)+"
)
NUMBERED_PREFIX_RE = re.compile(r"^\s*\d+\s*[.)]\s*")

DATE_RANGE_RE = re.compile(
    r"(?P<start>(?:\d{1,2}/\d{4}|\d{4}|[A-Za-z]{3,9}\s+\d{4}))"
    r"\s*(?:-|–|—|to)\s*"
    r"(?P<end>present|current|\d{1,2}/\d{4}|\d{4}|[A-Za-z]{3,9}\s+\d{4})",
    re.I,
)


def _normalize_text(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\u200b", "").replace("\uf0b7", "•")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _header_key(line: str) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", line.upper()).strip()


def _section_for_line(line: str) -> str | None:
    key = _header_key(line)
    for section, aliases in SECTION_ALIASES.items():
        if key in {_header_key(alias) for alias in aliases}:
            return section
    return None


def _strip_bullet(line: str) -> tuple[str, bool]:
    """Strip decorative and numbered bullets without losing whether a bullet existed."""
    cleaned, found_bullet = line.strip(), False

    while True:
        before = cleaned
        cleaned = BULLET_PREFIX_RE.sub("", cleaned, count=1)

        if cleaned != before:
            found_bullet = True
            continue

        numbered = NUMBERED_PREFIX_RE.sub("", cleaned, count=1)
        if numbered != cleaned:
            cleaned = numbered
            continue

        break

    return cleaned.strip(), found_bullet


def _dedupe(items: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for item in items:
        value = re.sub(r"\s+", " ", item).strip()
        if value and value.casefold() not in seen:
            result.append(value)
            seen.add(value.casefold())

    return result


def extract_technologies(text: str) -> list[str]:
    """Find recognized skills and return their canonical names in text order."""
    matches: list[tuple[int, str]] = []

    for canonical, aliases in TECHNOLOGY_ALIASES.items():
        positions: list[int] = []

        for alias in aliases:
            pattern = re.compile(
                rf"(?<![A-Za-z0-9+#]){re.escape(alias)}(?![A-Za-z0-9+#])",
                re.I,
            )
            match = pattern.search(text)
            if match:
                positions.append(match.start())

        if positions:
            matches.append((min(positions), canonical))

    matches.sort(key=lambda item: item[0])
    return _dedupe(name for _, name in matches)


def _parse_sections(
    lines: list[str],
) -> tuple[list[str], dict[str, list[str]]]:
    preamble: list[str] = []
    sections: dict[str, list[str]] = {}
    current = None

    for line in lines:
        name = _section_for_line(line)

        if name:
            current = name
            sections.setdefault(current, [])
        elif current is None:
            preamble.append(line)
        else:
            sections[current].append(line)

    return preamble, sections


def _parse_contact(lines: list[str]) -> ResumeContact:
    all_text = "\n".join(lines)
    email = re.search(
        r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
        all_text,
        re.I,
    )
    linkedin = re.search(
        r"(?:https?://)?(?:www\.)?linkedin\.com/[^\s|]+",
        all_text,
        re.I,
    )
    github = re.search(
        r"(?:https?://)?(?:www\.)?github\.com/[^\s|]+",
        all_text,
        re.I,
    )

    phone_pattern = re.compile(r"^\s*\+?\d[\d\s().-]{8,}\d\s*$")
    phone_line = next(
        (
            line
            for line in lines
            if "@"
            not in line
            and "linkedin.com/" not in line.casefold()
            and "github.com/" not in line.casefold()
            and phone_pattern.match(line)
        ),
        None,
    )

    name = None
    for line in lines:
        lower = line.casefold()
        if (
            "@"
            in line
            or "linkedin.com/" in lower
            or "github.com/" in lower
            or _section_for_line(line)
        ):
            continue
        if phone_pattern.match(line):
            continue
        if len(line.split()) >= 2 and len(line) <= 70:
            name = line.strip(" |,;")
            break

    location = None
    for line in reversed(lines):
        if (
            ","
            in line
            and "@"
            not in line
            and "linkedin.com/" not in line.casefold()
            and "github.com/" not in line.casefold()
            and not phone_pattern.match(line)
        ):
            location = re.sub(r"\s*,\s*", ", ", line).strip(" ,")
            break

    def clean_url(match: re.Match[str] | None) -> str | None:
        if not match:
            return None
        value = match.group(0).rstrip(".,;)")
        value = re.sub(r"^https?://", "", value, flags=re.I)
        return re.sub(r"^www\.", "", value, flags=re.I)

    return ResumeContact(
        name=name,
        email=email.group(0) if email else None,
        phone=re.sub(r"\s+", " ", phone_line).strip() if phone_line else None,
        linkedin=clean_url(linkedin),
        github=clean_url(github),
        location=location,
    )


def _parse_education(lines: list[str]) -> list[ResumeEducation]:
    if not lines:
        return []

    normalized: list[str] = []
    for line in lines:
        if normalized and normalized[-1].endswith(",") and not line.startswith(("•", "-")):
            normalized[-1] = f"{normalized[-1]} {line}"
        else:
            normalized.append(line.strip())

    degree_re = re.compile(
        r"\b(B\s*\.?\s*Tech|BTech|Bachelor(?:'s)?|M\s*\.?\s*Tech|MTech|"
        r"Master(?:'s)?|Ph\.?D|PhD|B\.?Sc|M\.?Sc)\b",
        re.I,
    )
    index = next(
        (i for i, line in enumerate(normalized) if degree_re.search(line)),
        None,
    )

    if index is None:
        return [ResumeEducation(raw_text="\n".join(normalized))]

    degree_line = normalized[index]
    match = degree_re.search(degree_line)
    token = re.sub(r"[ .]", "", match.group(0)).casefold() if match else ""

    if token in {"btech", "bachelor", "bachelor's", "bsc"}:
        degree = "Bachelor"
    elif token in {"mtech", "master", "master's", "msc"}:
        degree = "Master"
    elif token == "phd":
        degree = "PhD"
    else:
        degree = token.title() or None

    study_field = (
        degree_line[match.end():].strip(" -:|–—") if match else None
    )
    institution = next(
        (
            line.strip(" •-–—")
            for line in normalized[index + 1:]
            if re.search(r"\b(university|college|institute|school)\b", line, re.I)
        ),
        None,
    )

    cgpa = None
    for line in normalized:
        score = re.search(r"(?:CGPA|GPA)\s*[:=-]?\s*(\d+(?:\.\d+)?)", line, re.I)
        if score:
            cgpa = float(score.group(1))
            break

    date = next(
        (found for line in normalized if (found := DATE_RANGE_RE.search(line))),
        None,
    )
    location = next(
        (
            re.sub(r"\s*,\s*", ", ", line).strip(" ,")
            for line in normalized
            if ","
            in line
            and re.search(
                r"\b(India|Andhra Pradesh|Telangana|Karnataka|Hyderabad|Vijayawada|Nalgonda)\b",
                line,
                re.I,
            )
        ),
        None,
    )

    return [
        ResumeEducation(
            degree=degree,
            field_of_study=study_field or None,
            institution=institution,
            cgpa=cgpa,
            start_date=date.group("start") if date else None,
            end_date=date.group("end") if date else None,
            location=location,
            raw_text="\n".join(normalized),
        )
    ]


def _is_project_title(text: str, is_bullet: bool) -> bool:
    if (
        is_bullet
        or not text
        or len(text) > 55
        or len(text.split()) > 7
        or re.search(r"[.!?]$", text)
    ):
        return False

    if re.match(
        r"^(?:technologies|tech stack|role|company|project\s*\d*\s*:?)\b",
        text,
        re.I,
    ):
        return False

    if re.match(
        r"^(?:a|an|the|i\b|we\b|my\b|built\b|developed\b|created\b|"
        r"implemented\b|integrated\b|achieved\b|achieving\b|deployed\b|"
        r"designed\b|engineered\b|used\b|utilized\b|leveraged\b|worked\b|"
        r"responsible\b|this\b|it\b|to\b|for\b)",
        text,
        re.I,
    ):
        return False

    return bool(re.search(r"[A-Za-z]", text))


def _parse_projects(lines: list[str]) -> list[ResumeProject]:
    projects: list[ResumeProject] = []
    current = None

    for line in lines:
        text, is_bullet = _strip_bullet(line)
        if not text or text.casefold() == "languages/tools/frameworks/concepts":
            continue

        if _is_project_title(text, is_bullet):
            current = ResumeProject(name=text)
            projects.append(current)
        elif current is not None and re.match(
            r"^(?:technologies|tech stack)\s*:", text, re.I
        ):
            current.technologies = _dedupe(
                [
                    *current.technologies,
                    *extract_technologies(text.split(":", 1)[1]),
                ]
            )
        elif current is not None:
            # Bullets are always evidence for the current project, never new titles.
            current.bullets.append(text)

    for project in projects:
        content = " ".join([project.name, *project.bullets])
        project.technologies = _dedupe(
            [*project.technologies, *extract_technologies(content)]
        )
        project.description = " ".join(project.bullets).strip()

    return projects


def _parse_experience(lines: list[str]) -> list[ResumeExperience]:
    experiences: list[ResumeExperience] = []
    current = None
    role_re = re.compile(
        r"\b(intern|engineer|developer|analyst|manager|consultant|associate|"
        r"administrator|architect|designer|specialist|lead|officer)\b",
        re.I,
    )

    for line in lines:
        text, is_bullet = _strip_bullet(line)
        if not text:
            continue

        date = DATE_RANGE_RE.search(text)
        if date and current:
            current.start_date = date.group("start")
            current.end_date = date.group("end")
            continue

        if text.casefold() in {"remote", "hybrid", "onsite", "on-site"} and current:
            current.location = text
            continue

        parts = re.split(r"\s+[-–—]\s+", text, maxsplit=1)
        if len(parts) == 2 and role_re.search(parts[1]) and len(parts[0]) <= 90:
            current = ResumeExperience(
                company=parts[0].strip(),
                role=parts[1].strip(),
            )
            experiences.append(current)
            continue

        if (
            current is None
            and role_re.search(text)
            and len(text.split()) <= 10
            and not text.lower().startswith("project")
        ):
            current = ResumeExperience(role=text)
            experiences.append(current)
            continue

        if current is None:
            continue

        if re.match(r"^project\s*\d*\s*:", text, re.I) or is_bullet or not current.bullets:
            current.bullets.append(text)
        else:
            # Unbulleted PDF line wraps continue the previous detail.
            current.bullets[-1] = f"{current.bullets[-1]} {text}".strip()

    return experiences


def _parse_certifications(lines: list[str]) -> list[ResumeCertification]:
    merged: list[str] = []
    continuation_re = re.compile(
        r"^(?:fundamentals\b|certification\b|certificate\b|certified\b|"
        r"specialization\b|specialty\b|associate\b|professional\b|"
        r"practitioner\b|\(az\d+\)|az\d+\b|of\b|in\b|for\b|and\b|combined\b)",
        re.I,
    )

    for line in lines:
        text, _ = _strip_bullet(line)
        text = text.strip(" •-–—")
        if not text:
            continue

        if merged and (
            continuation_re.match(text)
            or merged[-1].rstrip().endswith(("-", "/", "(", ":"))
        ):
            merged[-1] = f"{merged[-1]} {text}".strip()
        else:
            merged.append(text)

    result = []
    for name in _dedupe(merged):
        issuer_match = re.search(
            r"\b(HackerRank|Hacker Rank|NPTEL|AWS|Microsoft)\b",
            name,
            re.I,
        )
        result.append(
            ResumeCertification(
                name=name,
                issuer=issuer_match.group(1) if issuer_match else None,
            )
        )

    return result


def _parse_achievements(lines: list[str]) -> list[str]:
    achievements: list[str] = []
    new_item_re = re.compile(
        r"^(?:achieved|solved|earned|won|ranked|secured|completed|recognized|received)\b",
        re.I,
    )

    for line in lines:
        text, is_bullet = _strip_bullet(line)
        if not text:
            continue

        if is_bullet or not achievements or new_item_re.match(text):
            achievements.append(text)
        else:
            # Join soft-wrapped PDF lines into the preceding achievement.
            achievements[-1] = f"{achievements[-1]} {text}".strip()

    return achievements


class ResumeParser:
    """Deterministically parse text-based PDF, TXT, and Markdown resumes."""

    SUPPORTED_SUFFIXES = {".pdf", ".txt", ".md", ".markdown"}

    def parse_file(self, file_path: str | Path) -> ParsedResume:
        path = Path(file_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Resume file not found: {path}")

        suffix = path.suffix.casefold()
        if suffix not in self.SUPPORTED_SUFFIXES:
            raise ValueError(
                f"Unsupported resume format '{suffix}'. Supported formats: PDF, TXT, MD."
            )

        if suffix == ".pdf":
            try:
                import pymupdf
            except ImportError as exc:
                raise RuntimeError(
                    "PyMuPDF is required for PDFs. Install it with: pip install pymupdf"
                ) from exc

            with pymupdf.open(path) as document:
                text = "\n".join(page.get_text("text") for page in document)
        else:
            text = path.read_text(encoding="utf-8", errors="replace")

        return self.parse_text(text)

    def parse_text(self, text: str) -> ParsedResume:
        normalized = _normalize_text(text)
        preamble, sections = _parse_sections(
            normalized.splitlines() if normalized else []
        )
        skills = extract_technologies("\n".join(sections.get("skills", [])))

        return ParsedResume(
            raw_text=normalized,
            contact=_parse_contact(preamble),
            skills=skills,
            programming_languages=[s for s in skills if s in PROGRAMMING_LANGUAGES],
            frameworks=[s for s in skills if s in FRAMEWORKS],
            tools=[s for s in skills if s in TOOLS],
            concepts=[s for s in skills if s in CONCEPTS],
            education=_parse_education(sections.get("education", [])),
            projects=_parse_projects(sections.get("projects", [])),
            experience=_parse_experience(sections.get("experience", [])),
            certifications=_parse_certifications(sections.get("certifications", [])),
            achievements=_parse_achievements(sections.get("achievements", [])),
            sections=sections,
        )


def parse_resume_file(file_path: str | Path) -> ParsedResume:
    """Convenience wrapper for code that does not need a ResumeParser instance."""
    return ResumeParser().parse_file(file_path)


__all__ = [
    "ParsedResume",
    "ResumeCertification",
    "ResumeContact",
    "ResumeEducation",
    "ResumeExperience",
    "ResumeParser",
    "ResumeProject",
    "extract_technologies",
    "parse_resume_file",
]