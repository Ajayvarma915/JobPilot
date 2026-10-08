from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
import re
from typing import Any


@dataclass
class ResumeContact:
    name: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    github: str = ""
    location: str = ""


@dataclass
class ResumeEducation:
    degree: str
    institution: str
    field_of_study: str = ""
    cgpa: str = ""
    start_date: str = ""
    end_date: str = ""
    location: str = ""


@dataclass
class ResumeProject:
    name: str
    description: str = ""
    bullets: list[str] = field(default_factory=list)
    technologies: list[str] = field(default_factory=list)


@dataclass
class ResumeExperience:
    company: str
    role: str
    experience_type: str = "internship"
    start_date: str = ""
    end_date: str = ""
    location: str = ""
    bullets: list[str] = field(default_factory=list)
    technologies: list[str] = field(default_factory=list)


@dataclass
class ResumeCertification:
    name: str


@dataclass
class ParsedResume:
    contact: ResumeContact = field(
        default_factory=ResumeContact
    )

    summary: str = ""

    skills: list[str] = field(
        default_factory=list
    )

    programming_languages: list[str] = field(
        default_factory=list
    )

    frameworks: list[str] = field(
        default_factory=list
    )

    tools: list[str] = field(
        default_factory=list
    )

    concepts: list[str] = field(
        default_factory=list
    )

    education: list[ResumeEducation] = field(
        default_factory=list
    )

    projects: list[ResumeProject] = field(
        default_factory=list
    )

    experience: list[ResumeExperience] = field(
        default_factory=list
    )

    certifications: list[ResumeCertification] = field(
        default_factory=list
    )

    achievements: list[str] = field(
        default_factory=list
    )

    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResumeParser:
    """
    Deterministic resume parser.

    Supported input:
        - PDF
        - plain text

    The parser intentionally does not use an LLM.
    It converts a resume into a structured representation
    that JobPilot can later use for matching and tailoring.
    """

    SECTION_ALIASES = {
        "education": {
            "education",
        },
        "skills": {
            "technical skills",
            "skills",
            "technical skill",
        },
        "projects": {
            "projects",
            "project",
        },
        "experience": {
            "experience",
            "work experience",
            "professional experience",
            "internship",
            "internships",
            "virtual internship",
        },
        "certifications": {
            "certificates",
            "certifications",
            "certification",
        },
        "achievements": {
            "achievements",
            "achievement",
        },
        "summary": {
            "summary",
            "profile",
            "objective",
        },
    }

    TECHNOLOGY_ALIASES = {
        "Java",
        "Python",
        "JavaScript",
        "TypeScript",
        "C",
        "C++",
        "C#",
        "HTML",
        "CSS",
        "React.js",
        "Next.js",
        "Node.js",
        "Express.js",
        "Tailwind CSS",
        "Auth.js",
        "Firebase",
        "Chart.js",
        "MongoDB",
        "MySQL",
        "PostgreSQL",
        "Git",
        "GitHub",
        "Docker",
        "AWS",
        "Azure",
        "Google Cloud",
        "NLP",
        "Machine Learning",
        "Deep Learning",
        "Artificial Intelligence",
        "Data Structures and Algorithms",
        "OOP",
        "REST APIs",
        "JWT",
        "Multer",
        "Cloudinary",
        "Mongoose",
        "MongoDB",
        "PyWhatKit",
    }

    PROGRAMMING_LANGUAGES = {
        "Java",
        "Python",
        "JavaScript",
        "TypeScript",
        "C",
        "C++",
        "C#",
    }

    FRAMEWORKS = {
        "React.js",
        "Next.js",
        "Node.js",
        "Express.js",
        "Tailwind CSS",
        "Auth.js",
        "Mongoose",
    }

    TOOLS = {
        "Git",
        "GitHub",
        "Firebase",
        "Chart.js",
        "PyWhatKit",
        "Docker",
        "Cloudinary",
        "Multer",
    }

    CONCEPTS = {
        "Data Structures and Algorithms",
        "OOP",
        "NLP",
        "Machine Learning",
        "Artificial Intelligence",
        "REST APIs",
        "JWT",
        "CRUD",
        "Authentication",
        "Session Management",
    }

    def parse_file(
        self,
        file_path: str | Path,
    ) -> ParsedResume:
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(
                f"Resume file not found: {path}"
            )

        suffix = path.suffix.lower()

        if suffix == ".pdf":
            raw_text = self._extract_pdf_text(
                path
            )
        elif suffix in {".txt", ".md"}:
            raw_text = path.read_text(
                encoding="utf-8"
            )
        else:
            raise ValueError(
                "Unsupported resume format. "
                "Use PDF, TXT or MD."
            )

        return self.parse_text(
            raw_text
        )

    def parse_text(
        self,
        text: str,
    ) -> ParsedResume:
        clean_text = self._clean_text(
            text
        )

        sections = self._split_sections(
            clean_text
        )

        contact = self._extract_contact(
            clean_text
        )

        skills = self._extract_skills(
            sections.get("skills", "")
        )

        programming_languages = self._filter_technology_group(
            skills,
            self.PROGRAMMING_LANGUAGES,
        )

        frameworks = self._filter_technology_group(
            skills,
            self.FRAMEWORKS,
        )

        tools = self._filter_technology_group(
            skills,
            self.TOOLS,
        )

        concepts = self._filter_technology_group(
            skills,
            self.CONCEPTS,
        )

        education = self._extract_education(
            sections.get("education", "")
        )

        projects = self._extract_projects(
            sections.get("projects", "")
        )

        experience = self._extract_experience(
            sections.get("experience", "")
        )

        certifications = (
            self._extract_certifications(
                sections.get(
                    "certifications",
                    "",
                )
            )
        )

        achievements = (
            self._extract_achievements(
                sections.get(
                    "achievements",
                    "",
                )
            )
        )

        summary = self._extract_summary(
            sections.get(
                "summary",
                "",
            )
        )

        return ParsedResume(
            contact=contact,
            summary=summary,
            skills=skills,
            programming_languages=programming_languages,
            frameworks=frameworks,
            tools=tools,
            concepts=concepts,
            education=education,
            projects=projects,
            experience=experience,
            certifications=certifications,
            achievements=achievements,
            raw_text=clean_text,
        )

    def _extract_pdf_text(
        self,
        path: Path,
    ) -> str:
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError(
                "PyMuPDF is required to parse PDF resumes. "
                "Install it with: pip install pymupdf"
            ) from exc

        document = fitz.open(
            path
        )

        try:
            pages: list[str] = []

            for page in document:
                text = page.get_text(
                    "text"
                )

                if text:
                    pages.append(
                        text
                    )

            return "\n".join(pages)
        finally:
            document.close()

    def _split_sections(
        self,
        text: str,
    ) -> dict[str, str]:
        sections: dict[str, list[str]] = {}
        current = "other"

        sections[current] = []

        for raw_line in text.splitlines():
            line = raw_line.strip()

            if not line:
                continue

            heading = self._detect_section_heading(
                line
            )

            if heading is not None:
                current = heading

                if current not in sections:
                    sections[current] = []

                continue

            sections.setdefault(
                current,
                [],
            ).append(line)

        return {
            key: "\n".join(
                value
            ).strip()
            for key, value in sections.items()
        }

    def _detect_section_heading(
        self,
        line: str,
    ) -> str | None:
        normalized = self._normalize_heading(
            line
        )

        for section, aliases in (
            self.SECTION_ALIASES.items()
        ):
            if normalized in {
                self._normalize_heading(
                    alias
                )
                for alias in aliases
            }:
                return section

        return None

    def _normalize_heading(
        self,
        value: str,
    ) -> str:
        text = value.lower().strip()

        text = re.sub(
            r"[:\-–]+$",
            "",
            text,
        )

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return text

    def _extract_contact(
        self,
        text: str,
    ) -> ResumeContact:
        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        name = ""

        if lines:
            first_line = lines[0]

            if not self._detect_section_heading(
                first_line
            ):
                name = first_line

        email_match = re.search(
            r"\b[A-Za-z0-9._%+-]+@"
            r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
            text,
        )

        phone_match = re.search(
            r"(?<!\d)"
            r"(?:\+91[\s-]?)?"
            r"[6-9]\d{9}"
            r"(?!\d)",
            text,
        )

        linkedin_match = re.search(
            r"(?:https?://)?"
            r"(?:www\.)?"
            r"linkedin\.com/[^\s|]+",
            text,
            re.IGNORECASE,
        )

        github_match = re.search(
            r"(?:https?://)?"
            r"(?:www\.)?"
            r"github\.com/[^\s|]+",
            text,
            re.IGNORECASE,
        )

        location = self._extract_location(
            text
        )

        return ResumeContact(
            name=name,
            email=(
                email_match.group(0)
                if email_match
                else ""
            ),
            phone=(
                phone_match.group(0)
                if phone_match
                else ""
            ),
            linkedin=(
                linkedin_match.group(0)
                if linkedin_match
                else ""
            ),
            github=(
                github_match.group(0)
                if github_match
                else ""
            ),
            location=location,
        )

    def _extract_location(
        self,
        text: str,
    ) -> str:
        match = re.search(
            r"\b([A-Za-z .'-]+,\s*"
            r"(?:Telangana|Andhra Pradesh|Karnataka|"
            r"Maharashtra|Tamil Nadu|Kerala|"
            r"Delhi|Haryana|Gujarat|Rajasthan))\b",
            text,
            re.IGNORECASE,
        )

        if match:
            return match.group(1).strip()

        return ""

    def _extract_skills(
        self,
        text: str,
    ) -> list[str]:
        if not text:
            return []

        found: list[str] = []

        for technology in self.TECHNOLOGY_ALIASES:
            pattern = self._technology_pattern(
                technology
            )

            if re.search(
                pattern,
                text,
                re.IGNORECASE,
            ):
                found.append(
                    technology
                )

        # Preserve a predictable order rather than
        # depending on set iteration order.
        preferred_order = [
            "Java",
            "Python",
            "JavaScript",
            "TypeScript",
            "C",
            "C++",
            "C#",
            "HTML",
            "CSS",
            "React.js",
            "Tailwind CSS",
            "Next.js",
            "Node.js",
            "Express.js",
            "Auth.js",
            "Firebase",
            "Chart.js",
            "Git",
            "GitHub",
            "Docker",
            "Cloudinary",
            "Multer",
            "MongoDB",
            "MySQL",
            "PostgreSQL",
            "Data Structures and Algorithms",
            "OOP",
            "NLP",
            "Machine Learning",
            "Artificial Intelligence",
            "REST APIs",
            "JWT",
            "PyWhatKit",
        ]

        ordered = [
            item
            for item in preferred_order
            if item in found
        ]

        return self._dedupe(
            ordered
        )

    def _technology_pattern(
        self,
        technology: str,
    ) -> str:
        escaped = re.escape(
            technology
        )

        if technology in {
            "C++",
            "C#",
            "C",
        }:
            return (
                rf"(?<![A-Za-z0-9])"
                rf"{escaped}"
                rf"(?![A-Za-z0-9])"
            )

        return (
            rf"(?<![A-Za-z0-9])"
            rf"{escaped}"
            rf"(?![A-Za-z0-9])"
        )

    def _filter_technology_group(
        self,
        skills: list[str],
        group: set[str],
    ) -> list[str]:
        return [
            skill
            for skill in skills
            if skill in group
        ]

    def _extract_education(
        self,
        text: str,
    ) -> list[ResumeEducation]:
        if not text:
            return []

        result: list[ResumeEducation] = []

        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        degree_pattern = re.compile(
            r"\b("
            r"BTech|B\.Tech|Bachelor(?:'s)?"
            r"|MTech|M\.Tech|Master(?:'s)?"
            r"|PhD|Doctorate"
            r")\b",
            re.IGNORECASE,
        )

        current_degree = ""
        current_field = ""
        current_institution = ""
        current_cgpa = ""
        current_start = ""
        current_end = ""
        current_location = ""

        for line in lines:
            degree_match = degree_pattern.search(
                line
            )

            if degree_match:
                if (
                    current_degree
                    and current_institution
                ):
                    result.append(
                        ResumeEducation(
                            degree=current_degree,
                            institution=current_institution,
                            field_of_study=current_field,
                            cgpa=current_cgpa,
                            start_date=current_start,
                            end_date=current_end,
                            location=current_location,
                        )
                    )

                current_degree = (
                    self._normalize_degree(
                        degree_match.group(1)
                    )
                )

                remainder = (
                    line[:degree_match.start()]
                    + line[degree_match.end():]
                ).strip(
                    " :-"
                )

                if remainder:
                    current_field = remainder

                continue

            cgpa_match = re.search(
                r"\bCGPA\s*[:\-]?\s*"
                r"([0-9]+(?:\.[0-9]+)?)",
                line,
                re.IGNORECASE,
            )

            if cgpa_match:
                current_cgpa = (
                    cgpa_match.group(1)
                )
                continue

            date_match = re.search(
                r"\b(20\d{2})\s*[-–]\s*"
                r"(present|20\d{2})\b",
                line,
                re.IGNORECASE,
            )

            if date_match:
                current_start = (
                    date_match.group(1)
                )
                current_end = (
                    date_match.group(2)
                )
                continue

            if (
                current_degree
                and not current_institution
            ):
                if not degree_pattern.search(
                    line
                ):
                    current_institution = line
                    continue

            if (
                current_institution
                and not current_location
                and self._looks_like_location(
                    line
                )
            ):
                current_location = line
                continue

        if (
            current_degree
            and current_institution
        ):
            result.append(
                ResumeEducation(
                    degree=current_degree,
                    institution=current_institution,
                    field_of_study=current_field,
                    cgpa=current_cgpa,
                    start_date=current_start,
                    end_date=current_end,
                    location=current_location,
                )
            )

        return result

    def _normalize_degree(
        self,
        value: str,
    ) -> str:
        lower = value.lower()

        if (
            "phd" in lower
            or "doctor" in lower
        ):
            return "PhD"

        if (
            "mtech" in lower
            or "m.tech" in lower
            or "master" in lower
        ):
            return "Master"

        if (
            "btech" in lower
            or "b.tech" in lower
            or "bachelor" in lower
        ):
            return "Bachelor"

        return value

    def _looks_like_location(
        self,
        value: str,
    ) -> bool:
        return bool(
            re.search(
                r"\b(?:India|Telangana|"
                r"Andhra Pradesh|Karnataka|"
                r"Hyderabad|Vijayawada|"
                r"Nalgonda)\b",
                value,
                re.IGNORECASE,
            )
        )

    def _extract_projects(
        self,
        text: str,
    ) -> list[ResumeProject]:
        if not text:
            return []

        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        projects: list[ResumeProject] = []

        current: ResumeProject | None = None

        for line in lines:
            bullet = self._strip_bullet(
                line
            )

            if self._looks_like_project_title(
                line
            ):
                if current is not None:
                    current.technologies = (
                        self._extract_skills(
                            " ".join(
                                current.bullets
                            )
                            + " "
                            + current.description
                        )
                    )

                    projects.append(
                        current
                    )

                current = ResumeProject(
                    name=bullet
                )
                continue

            if current is None:
                continue

            if self._is_bullet(line):
                current.bullets.append(
                    bullet
                )
            elif not current.description:
                current.description = bullet
            else:
                current.description += (
                    " "
                    + bullet
                )

        if current is not None:
            current.technologies = (
                self._extract_skills(
                    " ".join(
                        current.bullets
                    )
                    + " "
                    + current.description
                )
            )

            projects.append(
                current
            )

        return projects

    def _looks_like_project_title(
        self,
        line: str,
    ) -> bool:
        if self._is_bullet(line):
            return False

        if not line:
            return False

        if len(line) > 80:
            return False

        lower = line.lower()

        excluded = {
            "virtual internship",
            "education",
            "technical skills",
            "certificates",
            "achievements",
        }

        if lower in excluded:
            return False

        return True

    def _extract_experience(
        self,
        text: str,
    ) -> list[ResumeExperience]:
        if not text:
            return []

        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        experiences: list[ResumeExperience] = []

        current: ResumeExperience | None = None

        for index, line in enumerate(lines):
            if self._looks_like_experience_header(
                line
            ):
                company, role = (
                    self._parse_experience_header(
                        line
                    )
                )

                if current is not None:
                    current.technologies = (
                        self._extract_skills(
                            " ".join(
                                current.bullets
                            )
                        )
                    )

                    experiences.append(
                        current
                    )

                current = ResumeExperience(
                    company=company,
                    role=role,
                )

                continue

            if current is None:
                continue

            date_match = re.search(
                r"(\d{2}/\d{4})\s*[-–]\s*"
                r"(\d{2}/\d{4})",
                line,
            )

            if date_match:
                current.start_date = (
                    date_match.group(1)
                )
                current.end_date = (
                    date_match.group(2)
                )
                continue

            if self._is_bullet(line):
                current.bullets.append(
                    self._strip_bullet(
                        line
                    )
                )
            elif (
                not current.location
                and self._looks_like_location(
                    line
                )
            ):
                current.location = line

        if current is not None:
            current.technologies = (
                self._extract_skills(
                    " ".join(
                        current.bullets
                    )
                )
            )

            experiences.append(
                current
            )

        return experiences

    def _looks_like_experience_header(
        self,
        line: str,
    ) -> bool:
        lower = line.lower()

        return (
            "intern" in lower
            or "engineer" in lower
            or "developer" in lower
        ) and not self._is_bullet(
            line
        )

    def _parse_experience_header(
        self,
        line: str,
    ) -> tuple[str, str]:
        if " - " in line:
            role, company = line.split(
                " - ",
                1,
            )
            return (
                company.strip(),
                role.strip(),
            )

        parts = line.split(
            " "
        )

        if len(parts) >= 3:
            role = " ".join(
                parts[:-1]
            )
            company = parts[-1]

            return (
                company,
                role,
            )

        return (
            line,
            "Experience",
        )

    def _extract_certifications(
        self,
        text: str,
    ) -> list[ResumeCertification]:
        if not text:
            return []

        result: list[
            ResumeCertification
        ] = []

        for line in text.splitlines():
            cleaned = self._strip_bullet(
                line.strip()
            )

            if cleaned:
                result.append(
                    ResumeCertification(
                        name=cleaned
                    )
                )

        return result

    def _extract_achievements(
        self,
        text: str,
    ) -> list[str]:
        if not text:
            return []

        result: list[str] = []

        for line in text.splitlines():
            cleaned = self._strip_bullet(
                line.strip()
            )

            if cleaned:
                result.append(
                    cleaned
                )

        return result

    def _extract_summary(
        self,
        text: str,
    ) -> str:
        if not text:
            return ""

        return " ".join(
            line.strip()
            for line in text.splitlines()
            if line.strip()
        )

    def _is_bullet(
        self,
        line: str,
    ) -> bool:
        return bool(
            re.match(
                r"^\s*(?:[-*•▪◦]|\d+[.)])\s+",
                line,
            )
        )

    def _strip_bullet(
        self,
        line: str,
    ) -> str:
        return re.sub(
            r"^\s*(?:[-*•▪◦]|\d+[.)])\s+",
            "",
            line,
        ).strip()

    def _clean_text(
        self,
        text: str,
    ) -> str:
        text = text.replace(
            "\r",
            "\n",
        )

        text = text.replace(
            "\xa0",
            " ",
        )

        text = re.sub(
            r"[ \t]+",
            " ",
            text,
        )

        text = re.sub(
            r"\n{3,}",
            "\n\n",
            text,
        )

        return text.strip()

    def _dedupe(
        self,
        values: list[str],
    ) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []

        for value in values:
            key = value.lower()

            if key in seen:
                continue

            seen.add(key)
            result.append(value)

        return result


def parse_resume_file(
    file_path: str | Path,
) -> ParsedResume:
    parser = ResumeParser()

    return parser.parse_file(
        file_path
    )


__all__ = [
    "ResumeContact",
    "ResumeEducation",
    "ResumeProject",
    "ResumeExperience",
    "ResumeCertification",
    "ParsedResume",
    "ResumeParser",
    "parse_resume_file",
]