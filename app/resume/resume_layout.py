"""One layout for every tailored resume, copied from your master resume.

The PDF and the DOCX builders both draw from the structure built here, so they cannot drift apart or
away from the master. The look (A4, Calibri 9.6 pt, bold uppercase headings with a thin black rule,
round bullets, the section order, grouped technical skills, blue links) was measured from the master
resume PDF. Nothing is written or rewritten here: every line is taken from verified evidence.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ---- the master resume's look (points; colours as hex) ----------------------------------------------------
STYLE = {
    "page": "A4",
    "margin_left": 46.0,
    "margin_right": 45.3,
    "margin_top": 33.0,
    "margin_bottom": 33.0,
    "name_size": 18.0,
    "name_leading": 21.6,
    "body_size": 9.6,
    "body_leading": 11.5,
    "heading_size": 10.6,
    "heading_leading": 13.0,
    "text": "#111111",
    "muted": "#333333",
    "link": "#1A4F9C",
    "rule": "#111111",
    "rule_width": 0.7,
    "bullet_indent": 11.0,
}

# The master's section order.
SECTION_ORDER = ("summary", "experience", "project", "skill", "education", "certification", "achievement")
SECTION_TITLES = {
    "summary": "Summary",
    "experience": "Experience",
    "project": "Projects",
    "skill": "Technical Skills",
    "education": "Education",
    "certification": "Certifications",
    "achievement": "Achievements",
}

_LINK_RE = re.compile(r"((?:https?://)?(?:www\.)?(?:github|linkedin|gitlab)\.com/\S+)", re.IGNORECASE)


@dataclass
class Run:
    text: str
    bold: bool = False
    italic: bool = False
    kind: str = "text"  # text | muted | link


@dataclass
class Line:
    runs: list[Run]
    style: str = "body"  # body | entry (a bold heading line of a job, project or degree) | sub (italic detail line)


@dataclass
class Bullet:
    runs: list[Run]


@dataclass
class Section:
    title: str
    items: list[Line | Bullet] = field(default_factory=list)


@dataclass
class LayoutDocument:
    name: str
    contact: list[list[Run]]
    sections: list[Section]


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _dates(metadata: dict[str, Any]) -> str:
    start, end = _clean(metadata.get("start_date")), _clean(metadata.get("end_date"))
    return f"{start} - {end}".strip(" -") if (start or end) else ""


def _with_links(text: str, *, italic: bool = False, kind: str = "muted") -> list[Run]:
    """Split a line so github.com/... style links are blue and the rest keeps its colour."""
    runs: list[Run] = []
    for part in _LINK_RE.split(text):
        if not part:
            continue
        runs.append(Run(part, italic=italic, kind="link" if _LINK_RE.fullmatch(part) else kind))
    return runs


def _contact(candidate: dict[str, Any]) -> list[list[Run]]:
    first = " | ".join(_clean(candidate.get(key)) for key in ("location", "phone", "email") if _clean(candidate.get(key)))
    links = " | ".join(_clean(candidate.get(key)) for key in ("linkedin", "github") if _clean(candidate.get(key)))
    lines: list[list[Run]] = []
    if first:
        lines.append([Run(first)])
    if links:
        lines.append([Run(links, kind="link")])
    return lines


def _experience(item: dict[str, Any]) -> list[Line | Bullet]:
    metadata = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
    parts = [_clean(metadata.get("role")), _clean(metadata.get("company")), _dates(metadata)]
    heading = " | ".join(part for part in parts if part) or _clean(item.get("title")) or "Experience"
    if _clean(metadata.get("location")):
        heading += f" | {_clean(metadata['location'])}"
    out: list[Line | Bullet] = [Line([Run(heading, bold=True)], "entry")]
    if _clean(metadata.get("context")):
        out.append(Line([Run(_clean(metadata["context"]), italic=True, kind="muted")], "sub"))
    bullets = metadata.get("bullets") if isinstance(metadata.get("bullets"), list) else []
    for bullet in bullets or ([item.get("statement")] if item.get("statement") else []):
        if _clean(bullet):
            out.append(Bullet([Run(_clean(bullet))]))
    return out


def _project(item: dict[str, Any]) -> list[Line | Bullet]:
    metadata = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
    out: list[Line | Bullet] = [Line([Run(_clean(item.get("title")) or "Project", bold=True)], "entry")]
    if _clean(metadata.get("tech_line")):
        out.append(Line(_with_links(_clean(metadata["tech_line"]), italic=True), "sub"))
    bullets = metadata.get("bullets") if isinstance(metadata.get("bullets"), list) else []
    for bullet in bullets or ([item.get("statement")] if item.get("statement") else []):
        if _clean(bullet):
            out.append(Bullet([Run(_clean(bullet))]))
    return out


def _education(item: dict[str, Any]) -> Line:
    metadata = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
    degree = ", ".join(part for part in (_clean(metadata.get("degree")), _clean(metadata.get("field_of_study"))) if part)
    institution = ", ".join(part for part in (_clean(metadata.get("institution")), _clean(metadata.get("location"))) if part)
    rest = [institution] if institution else []
    if metadata.get("cgpa") is not None:
        rest.append(f"CGPA: {metadata['cgpa']}")
    if _dates(metadata):
        rest.append(_dates(metadata))
    runs = [Run(degree or _clean(item.get("title")) or "Education", bold=True)]
    if rest:
        runs.append(Run(" | " + " | ".join(rest)))
    return Line(runs, "body")


def _skill_lines(records: list[dict[str, Any]], matches: list[str] | None = None) -> list[Line]:
    """Grouped like the master ("Languages: Java, Python"). Skills the job asks for come first inside each group.

    An older store without group details falls back to one plain list, as before.
    """
    placed = [r for r in records if isinstance(r.get("metadata"), dict) and "print_group" in r["metadata"]]
    if placed:
        # Skills you confirmed for this one resume have no place in your master's skills section yet. Programming
        # languages join "Languages"; anything else gets its own "Other Skills" line at the end.
        from app.resume.resume_parser import PROGRAMMING_LANGUAGES

        have_languages = any(r["metadata"]["print_group"] == "Languages" for r in placed)
        extra = [r for r in records if r not in placed and _clean(r.get("title"))]
        for offset, record in enumerate(extra):
            title = _clean(record.get("title"))
            label = "Languages" if (title in PROGRAMMING_LANGUAGES and have_languages) else "Other Skills"
            placed.append({**record, "metadata": {**(record.get("metadata") or {}), "print_group": label,
                                                  "print_order": 10_000 + offset, "print_text": title}})
    if not placed:
        names = list(dict.fromkeys(_clean(r.get("title")) for r in records if _clean(r.get("title"))))
        return [Line([Run(", ".join(names))])] if names else []
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in sorted(placed, key=lambda r: r["metadata"].get("print_order", 0)):
        groups.setdefault(str(record["metadata"]["print_group"]), []).append(record)
    lines: list[Line] = []
    asked_for = {name.casefold() for name in (matches or [])}
    if matches:
        lines.append(Line([Run("Relevant to this role: ", bold=True), Run(", ".join(matches))]))
    for label, members in groups.items():
        def wanted(record: dict[str, Any]) -> int:
            shown = _clean(record["metadata"].get("print_text") or record.get("title")).casefold()
            return 0 if shown in asked_for else 1

        ordered = sorted(members, key=lambda r: (wanted(r), r["metadata"].get("print_order", 0)))
        items = list(dict.fromkeys(_clean(r["metadata"].get("print_text") or r.get("title")) for r in ordered))
        lines.append(Line([Run(f"{label}: ", bold=True), Run(", ".join(items))]))
    return lines


def build_layout(records: list[dict[str, Any]], candidate: dict[str, Any], matches: list[str] | None = None) -> LayoutDocument:
    """Turn verified records into the master's layout. `matches` are the verified skills the posting asks for."""
    by_category: dict[str, list[dict[str, Any]]] = {}
    for item in records:
        by_category.setdefault(str(item.get("category", "")), []).append(item)

    sections: list[Section] = []
    for category in SECTION_ORDER:
        items = by_category.get(category, [])
        if not items:
            continue
        section = Section(SECTION_TITLES[category])
        if category == "summary":
            section.items.append(Line([Run(_clean(items[0].get("statement")))]))
        elif category == "experience":
            for item in items:
                section.items.extend(_experience(item))
        elif category == "project":
            for item in items:
                section.items.extend(_project(item))
        elif category == "skill":
            section.items.extend(_skill_lines(items, matches))
        elif category == "education":
            section.items.extend(_education(item) for item in items)
        elif category == "certification":
            names = list(dict.fromkeys(_clean(item.get("title") or item.get("statement")) for item in items))
            section.items.append(Line([Run(" | ".join(name for name in names if name))]))
        elif category == "achievement":
            section.items.extend(Bullet([Run(_clean(item.get("statement")))]) for item in items if _clean(item.get("statement")))
        if section.items:
            sections.append(section)
    return LayoutDocument(name=_clean(candidate.get("name")), contact=_contact(candidate), sections=sections)


__all__ = ["STYLE", "Bullet", "Line", "LayoutDocument", "Run", "Section", "build_layout"]
