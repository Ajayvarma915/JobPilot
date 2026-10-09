from __future__ import annotations

import hashlib
import json
import re
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.resume.resume_parser import (
    FRAMEWORKS,
    PROGRAMMING_LANGUAGES,
    TOOLS,
    TECHNOLOGY_ALIASES,
    ParsedResume,
    ResumeParser,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESUME_DIRECTORY = PROJECT_ROOT / "data" / "master_resume"
DEFAULT_STORE_PATH = DEFAULT_RESUME_DIRECTORY / "master_resume_evidence.json"
SCHEMA_VERSION = 1
SUPPORTED_RESUME_SUFFIXES = {".pdf", ".txt", ".md", ".markdown"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _normalized_key(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _stable_id(category: str, identity: str) -> str:
    payload = f"{category}\0{_normalized_key(identity)}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:20]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        cleaned = re.sub(r"\s+", " ", str(value)).strip()
        if cleaned and cleaned.casefold() not in seen:
            result.append(cleaned)
            seen.add(cleaned.casefold())

    return result


def _skill_source_lines(skill: str, skill_lines: list[str]) -> list[str]:
    """Find source lines for a normalized skill without matching substrings."""
    aliases = TECHNOLOGY_ALIASES.get(skill, (skill,))
    found: list[str] = []

    for line in skill_lines:
        for alias in aliases:
            pattern = re.compile(
                rf"(?<![A-Za-z0-9+#]){re.escape(alias)}(?![A-Za-z0-9+#])",
                re.IGNORECASE,
            )

            if pattern.search(line):
                found.append(line)
                break

    return _dedupe(found)


def _skill_group(skill: str) -> str:
    if skill in PROGRAMMING_LANGUAGES:
        return "programming_language"

    if skill in FRAMEWORKS:
        return "framework"

    if skill in TOOLS:
        return "tool"

    return "concept"


def _record(
    *,
    category: str,
    identity: str,
    title: str,
    statement: str,
    source_file: str,
    source_section: str,
    source_text: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a traceable record. Extraction is not user verification."""
    return {
        "evidence_id": _stable_id(category, identity),
        "category": category,
        "title": title,
        "statement": statement.strip(),
        "source": {
            "file": source_file,
            "section": source_section,
            "text": source_text.strip(),
        },
        "metadata": metadata or {},
        "review": {
            "status": "needs_review",
            "user_verified": False,
            "reviewed_at_utc": None,
            "note": None,
        },
    }


class MasterResumeEvidenceStore:
    """Build and maintain a JSON store of traceable resume evidence.

    New evidence is unverified by default. A record is marked verified only
    when set_verified() is called explicitly. Rebuilding preserves review
    status only when the record's statement and source text have not changed.
    """

    def __init__(self, store_path: str | Path | None = None) -> None:
        self.store_path = Path(store_path) if store_path else DEFAULT_STORE_PATH

    def build_from_file(
        self,
        resume_path: str | Path,
        *,
        preserve_review_status: bool = True,
    ) -> dict[str, Any]:
        source_path = Path(resume_path).expanduser().resolve()

        if not source_path.exists():
            raise FileNotFoundError(f"Resume file not found: {source_path}")

        if source_path.suffix.casefold() not in SUPPORTED_RESUME_SUFFIXES:
            supported = ", ".join(sorted(SUPPORTED_RESUME_SUFFIXES))
            raise ValueError(
                f"Unsupported resume format. Supported formats: {supported}"
            )

        parsed = ResumeParser().parse_file(source_path)

        return self.build_from_parsed(
            parsed,
            source_path=source_path,
            preserve_review_status=preserve_review_status,
        )

    def build_from_parsed(
        self,
        parsed: ParsedResume,
        *,
        source_path: str | Path,
        preserve_review_status: bool = True,
    ) -> dict[str, Any]:
        source = Path(source_path).expanduser().resolve()
        source_file = source.name
        skill_lines = parsed.sections.get("skills", [])
        evidence: list[dict[str, Any]] = []

        # Skills
        for skill in parsed.skills:
            lines = _skill_source_lines(skill, skill_lines)
            source_text = "\n".join(lines) if lines else skill

            evidence.append(
                _record(
                    category="skill",
                    identity=skill,
                    title=skill,
                    statement=f"Listed as a skill in the source resume: {skill}.",
                    source_file=source_file,
                    source_section="skills",
                    source_text=source_text,
                    metadata={"skill_group": _skill_group(skill)},
                )
            )

        # Education
        for education in parsed.education:
            identity = " | ".join(
                part
                for part in (
                    education.degree,
                    education.field_of_study,
                    education.institution,
                )
                if part
            ) or education.raw_text

            title = " — ".join(
                part
                for part in (
                    education.degree,
                    education.field_of_study,
                    education.institution,
                )
                if part
            ) or "Education entry"

            facts = []

            if education.degree:
                facts.append(education.degree)

            if education.field_of_study:
                facts.append(education.field_of_study)

            if education.institution:
                facts.append(f"at {education.institution}")

            if education.cgpa is not None:
                facts.append(f"CGPA {education.cgpa:g}")

            if education.start_date or education.end_date:
                facts.append(
                    f"dates {education.start_date or 'unknown'}"
                    f"–{education.end_date or 'unknown'}"
                )

            statement = "; ".join(facts) if facts else education.raw_text
            metadata = asdict(education)
            metadata.pop("raw_text", None)

            evidence.append(
                _record(
                    category="education",
                    identity=identity,
                    title=title,
                    statement=statement,
                    source_file=source_file,
                    source_section="education",
                    source_text=education.raw_text
                    or "\n".join(parsed.sections.get("education", [])),
                    metadata=metadata,
                )
            )

        # Projects
        for project in parsed.projects:
            details = _dedupe(project.bullets)
            statement = project.description or " ".join(details) or project.name
            source_text = "\n".join([project.name, *details])

            evidence.append(
                _record(
                    category="project",
                    identity=project.name,
                    title=project.name,
                    statement=statement,
                    source_file=source_file,
                    source_section="projects",
                    source_text=source_text,
                    metadata={
                        "technologies": _dedupe(project.technologies),
                        "bullets": details,
                    },
                )
            )

        # Work experience and internships
        for experience in parsed.experience:
            title_parts = [
                part for part in (experience.role, experience.company) if part
            ]
            title = " at ".join(title_parts) or "Experience entry"
            details = _dedupe(experience.bullets)
            statement = " ".join(details) or title

            source_lines = [title]

            if experience.start_date or experience.end_date:
                source_lines.append(
                    f"{experience.start_date or 'unknown'}"
                    f" – {experience.end_date or 'unknown'}"
                )

            if experience.location:
                source_lines.append(experience.location)

            source_lines.extend(details)

            evidence.append(
                _record(
                    category="experience",
                    identity=title,
                    title=title,
                    statement=statement,
                    source_file=source_file,
                    source_section="experience",
                    source_text="\n".join(source_lines),
                    metadata={
                        "company": experience.company,
                        "role": experience.role,
                        "start_date": experience.start_date,
                        "end_date": experience.end_date,
                        "location": experience.location,
                        "bullets": details,
                    },
                )
            )

        # Certifications
        for certification in parsed.certifications:
            evidence.append(
                _record(
                    category="certification",
                    identity=certification.name,
                    title=certification.name,
                    statement=(
                        "Certification listed on the source resume: "
                        f"{certification.name}."
                    ),
                    source_file=source_file,
                    source_section="certifications",
                    source_text=certification.name,
                    metadata={"issuer": certification.issuer},
                )
            )

        # Achievements
        for index, achievement in enumerate(parsed.achievements, start=1):
            evidence.append(
                _record(
                    category="achievement",
                    identity=achievement,
                    title=f"Achievement {index}",
                    statement=achievement,
                    source_file=source_file,
                    source_section="achievements",
                    source_text=achievement,
                    metadata={"sequence": index},
                )
            )

        # Preserve a user's verification only if the same evidence is unchanged.
        existing = None

        if preserve_review_status and self.store_path.exists():
            try:
                existing = self.load()
            except (OSError, json.JSONDecodeError, ValueError):
                existing = None

        if existing:
            old_by_id = {
                item.get("evidence_id"): item
                for item in existing.get("evidence", [])
                if item.get("evidence_id")
            }

            for item in evidence:
                old = old_by_id.get(item["evidence_id"])

                if not old:
                    continue

                old_source = old.get("source", {}).get("text", "")
                old_statement = old.get("statement", "")
                new_source = item["source"]["text"]
                new_statement = item["statement"]

                if old_source == new_source and old_statement == new_statement:
                    old_review = old.get("review", {})
                    item["review"] = {
                        "status": old_review.get("status", "needs_review"),
                        "user_verified": bool(
                            old_review.get("user_verified", False)
                        ),
                        "reviewed_at_utc": old_review.get("reviewed_at_utc"),
                        "note": old_review.get("note"),
                    }

        source_metadata = {
            "file": source_file,
            "absolute_path": str(source),
            "format": source.suffix.casefold(),
            "sha256": (
                _sha256_file(source)
                if source.exists() and source.is_file()
                else None
            ),
        }

        store_data: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "created_at_utc": _utc_now(),
            "source_resume": source_metadata,
            "candidate": asdict(parsed.contact),
            "evidence_count": len(evidence),
            "counts_by_category": self._count_categories(evidence),
            "evidence": evidence,
        }

        self.save(store_data)
        return store_data

    def save(self, data: dict[str, Any]) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                delete=False,
                dir=self.store_path.parent,
                prefix=f".{self.store_path.name}.",
                suffix=".tmp",
            ) as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                temp_path = Path(handle.name)

            temp_path.replace(self.store_path)

        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)

    def load(self) -> dict[str, Any]:
        if not self.store_path.exists():
            raise FileNotFoundError(
                f"Evidence store not found: {self.store_path}"
            )

        with self.store_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        if (
            not isinstance(data, dict)
            or data.get("schema_version") != SCHEMA_VERSION
        ):
            raise ValueError(
                "Evidence store has an unsupported or invalid schema version."
            )

        if not isinstance(data.get("evidence"), list):
            raise ValueError("Evidence store is missing the evidence list.")

        return data

    def list_evidence(
        self,
        *,
        category: str | None = None,
        query: str | None = None,
        user_verified: bool | None = None,
    ) -> list[dict[str, Any]]:
        data = self.load()
        results = data["evidence"]

        if category:
            wanted = category.casefold().strip()
            results = [
                item
                for item in results
                if item.get("category", "").casefold() == wanted
            ]

        if query:
            wanted = query.casefold().strip()
            results = [
                item
                for item in results
                if wanted in item.get("title", "").casefold()
                or wanted in item.get("statement", "").casefold()
                or wanted
                in item.get("source", {}).get("text", "").casefold()
            ]

        if user_verified is not None:
            results = [
                item
                for item in results
                if bool(
                    item.get("review", {}).get("user_verified", False)
                ) is user_verified
            ]

        return results

    def set_verified(
        self,
        evidence_id: str,
        verified: bool = True,
        note: str | None = None,
    ) -> dict[str, Any]:
        data = self.load()

        target = next(
            (
                item
                for item in data["evidence"]
                if item.get("evidence_id") == evidence_id
            ),
            None,
        )

        if target is None:
            raise KeyError(f"Evidence record not found: {evidence_id}")

        target["review"] = {
            "status": "verified" if verified else "needs_review",
            "user_verified": bool(verified),
            "reviewed_at_utc": _utc_now() if verified else None,
            "note": note,
        }

        self.save(data)
        return target

    @staticmethod
    def _count_categories(
        evidence: list[dict[str, Any]],
    ) -> dict[str, int]:
        counts: dict[str, int] = {}

        for item in evidence:
            category = item["category"]
            counts[category] = counts.get(category, 0) + 1

        return dict(sorted(counts.items()))


def discover_master_resume(
    directory: str | Path = DEFAULT_RESUME_DIRECTORY,
) -> Path:
    """Select the only supported resume in the folder; reject ambiguity."""
    folder = Path(directory).expanduser().resolve()

    if not folder.exists():
        raise FileNotFoundError(
            f"Resume folder not found: {folder}. "
            "Add a PDF/TXT/MD resume or pass --resume."
        )

    candidates = sorted(
        path
        for path in folder.iterdir()
        if path.is_file()
        and path.suffix.casefold() in SUPPORTED_RESUME_SUFFIXES
    )

    if not candidates:
        raise FileNotFoundError(
            f"No supported resume found in {folder}. "
            "Add a PDF/TXT/MD resume or pass --resume."
        )

    if len(candidates) > 1:
        names = ", ".join(path.name for path in candidates)
        raise ValueError(
            "More than one resume was found; select one explicitly "
            "with --resume: " + names
        )

    return candidates[0]


__all__ = [
    "DEFAULT_RESUME_DIRECTORY",
    "DEFAULT_STORE_PATH",
    "MasterResumeEvidenceStore",
    "discover_master_resume",
]