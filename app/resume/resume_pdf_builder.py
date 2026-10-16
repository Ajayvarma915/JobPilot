from __future__ import annotations

import re
from html import escape
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from app.resume.resume_builder import ResumeBuildError, _validated_records


NAVY = colors.HexColor("#1F3756")
DARK = colors.HexColor("#23262A")
DARK_HEX = "#23262A"
MUTED = colors.HexColor("#565E69")
MUTED_HEX = "#565E69"
RULE = colors.HexColor("#C6D0DB")


def _safe(value: Any) -> str:
    """Escape source-backed text for ReportLab's paragraph mini-HTML parser."""
    text = str(value or "")
    text = re.sub(r"\s+", " ", text).strip()
    return escape(text, quote=False)


def _contact_lines(candidate: dict[str, Any]) -> list[str]:
    parts = [candidate.get("email"), candidate.get("phone"), candidate.get("location")]
    first = "  |  ".join(str(value).strip() for value in parts if value and str(value).strip())
    links = [candidate.get("linkedin"), candidate.get("github")]
    second = "  |  ".join(str(value).strip() for value in links if value and str(value).strip())
    return [value for value in (first, second) if value]


def _paragraph(text: Any, style: ParagraphStyle) -> Paragraph:
    # Explicitly normalize newlines before escaping. Newlines in source content
    # should not be interpreted as markup or silently create malformed XML.
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    return Paragraph(escape(cleaned, quote=False), style)


def _bullet_paragraph(text: Any, styles: dict[str, ParagraphStyle]) -> Paragraph | None:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return None
    return Paragraph(
        f'<font color="{DARK_HEX}">&#8226;</font>&nbsp;&nbsp;{escape(cleaned, quote=False)}',
        styles["bullet"],
    )


def _entry_heading(
    story: list[Any], title: str, detail: str | None, styles: dict[str, ParagraphStyle]
) -> None:
    headline = escape(re.sub(r"\s+", " ", str(title or "")).strip(), quote=False)
    if detail:
        detail_text = escape(re.sub(r"\s+", " ", str(detail)).strip(), quote=False)
        content = f"<b>{headline}</b> <font color='{MUTED_HEX}'> | {detail_text}</font>"
    else:
        content = f"<b>{headline}</b>"
    story.append(Paragraph(content, styles["entry"]))


def _render_education(story: list[Any], item: dict[str, Any], styles: dict[str, ParagraphStyle]) -> None:
    metadata = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
    title_parts = [metadata.get("degree"), metadata.get("field_of_study")]
    title = " — ".join(str(value).strip() for value in title_parts if value)
    if not title:
        title = str(item.get("title") or "Education")

    details: list[str] = []
    for key, label in (("institution", None), ("cgpa", "CGPA"), ("start_date", None)):
        value = metadata.get(key)
        if value is not None and str(value).strip():
            details.append(f"{label}: {value}" if label else str(value))
    end_date = metadata.get("end_date")
    if end_date and (not metadata.get("start_date") or str(end_date) != str(metadata.get("start_date"))):
        details.append(str(end_date))
    if metadata.get("location"):
        details.append(str(metadata["location"]))

    _entry_heading(story, title, " | ".join(details) if details else None, styles)


def _render_experience(story: list[Any], item: dict[str, Any], styles: dict[str, ParagraphStyle]) -> None:
    metadata = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
    title_parts = [metadata.get("role"), metadata.get("company")]
    title = " — ".join(str(value).strip() for value in title_parts if value)
    title = title or str(item.get("title") or "Experience")
    date_parts = [metadata.get("start_date"), metadata.get("end_date")]
    detail = " - ".join(str(value).strip() for value in date_parts if value)
    if metadata.get("location"):
        detail = f"{detail} | {metadata['location']}" if detail else str(metadata["location"])

    block: list[Any] = []
    _entry_heading(block, title, detail or None, styles)
    bullets = metadata.get("bullets", [])
    if not isinstance(bullets, list):
        bullets = []
    if not bullets and item.get("statement"):
        bullets = [item["statement"]]
    for value in bullets:
        bullet = _bullet_paragraph(value, styles)
        if bullet:
            block.extend([bullet, Spacer(1, 1.5)])
    story.append(KeepTogether(block))


def _render_project(story: list[Any], item: dict[str, Any], styles: dict[str, ParagraphStyle]) -> None:
    block: list[Any] = []
    _entry_heading(block, str(item.get("title") or "Project"), None, styles)
    metadata = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
    bullets = metadata.get("bullets", [])
    if not isinstance(bullets, list):
        bullets = []
    if not bullets and item.get("statement"):
        bullets = [item["statement"]]
    for value in bullets:
        bullet = _bullet_paragraph(value, styles)
        if bullet:
            block.extend([bullet, Spacer(1, 1.5)])
    story.append(KeepTogether(block))


def build_tailored_resume_pdf(
    selection: dict[str, Any],
    store: dict[str, Any],
    output_path: str | Path,
) -> Path:
    """Create a selectable-text, one-column PDF from currently verified evidence.

    The same validation routine used by the DOCX builder is run before rendering.
    Content is not generated or rewritten here; source-verified statements are
    formatted only. The layout intentionally avoids photos, tables, columns,
    icons, and text boxes to favor reliable parsing.
    """
    candidate = store.get("candidate")
    if not isinstance(candidate, dict) or not candidate.get("name"):
        raise ResumeBuildError("Evidence store has no candidate name.")

    records = _validated_records(selection, store)
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    base = getSampleStyleSheet()
    styles: dict[str, ParagraphStyle] = {
        "name": ParagraphStyle(
            "JobPilotResumeName", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=18, leading=21, textColor=NAVY, alignment=TA_CENTER,
            spaceAfter=2, keepWithNext=True,
        ),
        "contact": ParagraphStyle(
            "JobPilotResumeContact", parent=base["Normal"], fontName="Helvetica",
            fontSize=8.1, leading=10, textColor=MUTED, alignment=TA_CENTER,
            spaceAfter=1, splitLongWords=True,
        ),
        "section": ParagraphStyle(
            "JobPilotResumeSection", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=10.2, leading=12, textColor=NAVY, alignment=TA_LEFT,
            spaceBefore=5.5, spaceAfter=2.5, keepWithNext=True,
        ),
        "entry": ParagraphStyle(
            "JobPilotResumeEntry", parent=base["Normal"], fontName="Helvetica",
            fontSize=9.2, leading=11, textColor=DARK, spaceBefore=2,
            spaceAfter=1.5, keepWithNext=True, splitLongWords=True,
        ),
        "body": ParagraphStyle(
            "JobPilotResumeBody", parent=base["Normal"], fontName="Helvetica",
            fontSize=9.1, leading=11.3, textColor=DARK, spaceAfter=1.5,
            splitLongWords=True, wordWrap="LTR",
        ),
        "bullet": ParagraphStyle(
            "JobPilotResumeBullet", parent=base["Normal"], fontName="Helvetica",
            fontSize=9.1, leading=11.3, textColor=DARK,
            leftIndent=11, firstLineIndent=0, spaceAfter=1,
            splitLongWords=True, wordWrap="LTR",
        ),
    }

    by_category: dict[str, list[dict[str, Any]]] = {}
    for item in records:
        by_category.setdefault(str(item.get("category", "")), []).append(item)

    story: list[Any] = [_paragraph(candidate["name"], styles["name"])]
    for line in _contact_lines(candidate):
        story.append(_paragraph(line, styles["contact"]))
    story.append(Spacer(1, 3))

    def section(title: str) -> None:
        story.append(Paragraph(escape(title.upper()), styles["section"]))
        story.append(HRFlowable(width="100%", thickness=0.5, color=RULE, spaceBefore=0, spaceAfter=3))

    skill_records = by_category.get("skill", [])
    skill_names = list(dict.fromkeys(
        str(item.get("title", "")).strip()
        for item in skill_records
        if str(item.get("title", "")).strip()
    ))
    if skill_names:
        section("Technical Skills")
        story.append(_paragraph(", ".join(skill_names), styles["body"]))

    experience = by_category.get("experience", [])
    if experience:
        section("Experience")
        for item in experience:
            _render_experience(story, item, styles)

    projects = by_category.get("project", [])
    if projects:
        section("Projects")
        for item in projects:
            _render_project(story, item, styles)

    education = by_category.get("education", [])
    if education:
        section("Education")
        for item in education:
            _render_education(story, item, styles)

    certifications = by_category.get("certification", [])
    if certifications:
        section("Certifications")
        for item in certifications:
            bullet = _bullet_paragraph(item.get("title") or item.get("statement", ""), styles)
            if bullet:
                story.extend([bullet, Spacer(1, 1.5)])

    achievements = by_category.get("achievement", [])
    if achievements:
        section("Achievements")
        for item in achievements:
            bullet = _bullet_paragraph(item.get("statement", ""), styles)
            if bullet:
                story.extend([bullet, Spacer(1, 1.5)])

    title = f"Tailored Resume - {selection.get('job', {}).get('title', 'Job Application')}"
    document = SimpleDocTemplate(
        str(output),
        pagesize=LETTER,
        rightMargin=0.62 * inch,
        leftMargin=0.62 * inch,
        topMargin=0.48 * inch,
        bottomMargin=0.48 * inch,
        title=title[:240],
        author="JobPilot",
        subject="Resume generated from user-verified evidence",
    )

    def draw_footer(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawCentredString(LETTER[0] / 2, 0.25 * inch, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    return output


__all__ = ["build_tailored_resume_pdf"]
