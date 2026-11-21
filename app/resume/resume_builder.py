from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Mm, Pt, RGBColor

from app.resume.resume_layout import STYLE, Bullet, LayoutDocument, Line, Run, build_layout


class ResumeBuildError(ValueError):
    """Raised when a selection is unsafe, stale, or invalid for generation."""


NAVY = RGBColor(31, 55, 86)
DARK = RGBColor(35, 38, 42)
MUTED = RGBColor(86, 94, 105)


def _read_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"File not found: {resolved}")
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ResumeBuildError(f"Invalid JSON file: {resolved}") from exc
    if not isinstance(value, dict):
        raise ResumeBuildError(f"Expected a JSON object in {resolved}")
    return value


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return slug[:80] or "Tailored_Resume"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _set_run_font(run, *, size: float | None = None, bold: bool | None = None,
                  color: RGBColor | None = None, italic: bool | None = None) -> None:
    run.font.name = "Arial"
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), "Arial")
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), "Arial")
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color is not None:
        run.font.color.rgb = color
    if italic is not None:
        run.italic = italic


def _set_paragraph_spacing(paragraph, *, before: float = 0, after: float = 2,
                           line_spacing: float = 1.0) -> None:
    paragraph.paragraph_format.space_before = Pt(before)
    paragraph.paragraph_format.space_after = Pt(after)
    paragraph.paragraph_format.line_spacing = line_spacing
    paragraph.paragraph_format.keep_together = True


def _add_text(document: Document, text: str, *, size: float = 9.5,
              bold: bool = False, color: RGBColor = DARK,
              italic: bool = False, align=None, after: float = 2):
    paragraph = document.add_paragraph()
    if align is not None:
        paragraph.alignment = align
    _set_paragraph_spacing(paragraph, after=after)
    run = paragraph.add_run(text)
    _set_run_font(run, size=size, bold=bold, color=color, italic=italic)
    return paragraph


def _add_bullet(document: Document, text: str) -> None:
    cleaned = " ".join(str(text).split()).strip()
    if not cleaned:
        return
    paragraph = document.add_paragraph(style="List Bullet")
    paragraph.paragraph_format.left_indent = Inches(0.22)
    paragraph.paragraph_format.first_line_indent = Inches(-0.14)
    _set_paragraph_spacing(paragraph, after=1, line_spacing=1.0)
    run = paragraph.add_run(cleaned)
    _set_run_font(run, size=9.1, color=DARK)


def _add_section_heading(document: Document, title: str) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.keep_with_next = True
    _set_paragraph_spacing(paragraph, before=5, after=2)
    run = paragraph.add_run(title.upper())
    _set_run_font(run, size=10.5, bold=True, color=NAVY)

    # A light bottom border creates a clear heading divider without a table.
    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "5")
    bottom.set(qn("w:space"), "2")
    bottom.set(qn("w:color"), "C6D0DB")
    p_bdr.append(bottom)
    p_pr.append(p_bdr)


def _add_entry_heading(document: Document, title: str, detail: str | None = None) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.keep_with_next = True
    _set_paragraph_spacing(paragraph, before=2, after=1)
    run = paragraph.add_run(" ".join(str(title).split()))
    _set_run_font(run, size=9.6, bold=True, color=DARK)
    if detail:
        detail_run = paragraph.add_run(f"  |  {' '.join(str(detail).split())}")
        _set_run_font(detail_run, size=8.9, color=MUTED)


def _rgb(hex_colour: str) -> RGBColor:
    value = hex_colour.lstrip("#")
    return RGBColor(int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


_RUN_COLOURS = {"text": STYLE["text"], "muted": STYLE["muted"], "link": STYLE["link"]}


def _style_run(run, *, size: float, bold: bool = False, italic: bool = False, colour: str = STYLE["text"]) -> None:
    run.font.name = "Calibri"
    properties = run._element.get_or_add_rPr()
    for attribute in ("w:ascii", "w:hAnsi", "w:cs"):
        properties.rFonts.set(qn(attribute), "Calibri")
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    run.font.color.rgb = _rgb(colour)


def _fixed_line(paragraph, leading: float, *, before: float = 0, after: float = 0) -> None:
    paragraph.paragraph_format.space_before = Pt(before)
    paragraph.paragraph_format.space_after = Pt(after)
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    paragraph.paragraph_format.line_spacing = Pt(leading)


def _add_runs(paragraph, runs: list[Run], *, size: float, bold: bool = False, italic: bool = False) -> None:
    for run in runs:
        text = re.sub(r"\s+", " ", run.text)  # one space stays at either edge ("Languages: " + "Java")
        if not text.strip():
            continue
        piece = paragraph.add_run(text)
        _style_run(piece, size=size, bold=bold or run.bold, italic=italic or run.italic, colour=_RUN_COLOURS.get(run.kind, STYLE["text"]))


def _render_docx(layout: LayoutDocument) -> Document:
    """Draw the shared layout as a DOCX in the master resume's style (A4, Calibri, same sizes and spacing)."""
    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Mm(210), Mm(297)
    section.left_margin, section.right_margin = Pt(STYLE["margin_left"]), Pt(STYLE["margin_right"])
    section.top_margin, section.bottom_margin = Pt(STYLE["margin_top"]), Pt(STYLE["margin_bottom"])

    for style_name in ("Normal", "List Bullet"):
        style = document.styles[style_name]
        style.font.name = "Calibri"
        style._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), "Calibri")
        style._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), "Calibri")
        style.font.size = Pt(STYLE["body_size"])
        style.font.color.rgb = _rgb(STYLE["text"])

    body, leading = STYLE["body_size"], STYLE["body_leading"]
    name = document.add_paragraph()
    name.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _fixed_line(name, STYLE["name_leading"])
    _add_runs(name, [Run(layout.name)], size=STYLE["name_size"], bold=True)
    for contact in layout.contact:
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _fixed_line(paragraph, leading)
        _add_runs(paragraph, contact, size=body)

    for block in layout.sections:
        heading = document.add_paragraph()
        heading.paragraph_format.keep_with_next = True
        _fixed_line(heading, STYLE["heading_leading"], before=6, after=2)
        _add_runs(heading, [Run(block.title.upper())], size=STYLE["heading_size"], bold=True)
        borders = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "6")  # eighths of a point: 0.75 pt, like the master's rule
        bottom.set(qn("w:space"), "1")
        bottom.set(qn("w:color"), STYLE["rule"].lstrip("#"))
        borders.append(bottom)
        heading._p.get_or_add_pPr().append(borders)

        for item in block.items:
            if isinstance(item, Bullet):
                paragraph = document.add_paragraph(style="List Bullet")
                paragraph.paragraph_format.left_indent = Pt(STYLE["bullet_indent"])
                paragraph.paragraph_format.first_line_indent = Pt(-STYLE["bullet_indent"] + 1.5)
                _fixed_line(paragraph, leading)
                _add_runs(paragraph, item.runs, size=body)
                continue
            paragraph = document.add_paragraph()
            _fixed_line(paragraph, leading, before=1.5 if item.style == "entry" else 0)
            paragraph.paragraph_format.keep_with_next = item.style in {"entry", "sub"}
            _add_runs(paragraph, item.runs, size=body)
    return document


def _validated_records(selection: dict[str, Any], store: dict[str, Any]) -> list[dict[str, Any]]:
    safety = selection.get("safety", {})
    if safety.get("generated_claims") is True:
        raise ResumeBuildError("Selection report indicates generated claims; refusing to build.")
    if safety.get("only_user_verified_records_selected") is not True:
        raise ResumeBuildError("Selection report lacks the required verification-safety flag.")

    selected = selection.get("selected_evidence")
    if not isinstance(selected, list) or not selected:
        raise ResumeBuildError("No verified evidence was selected. Review evidence or select a suitable JD first.")

    current_by_id = {
        item.get("evidence_id"): item
        for item in store.get("evidence", [])
        if item.get("evidence_id")
    }

    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for selected_item in selected:
        evidence_id = selected_item.get("evidence_id")
        if not evidence_id or evidence_id in seen:
            raise ResumeBuildError("Selection contains a missing or duplicate evidence ID.")
        seen.add(evidence_id)

        current = current_by_id.get(evidence_id)
        if current is None:
            raise ResumeBuildError(f"Selected evidence no longer exists in the store: {evidence_id}")
        if current.get("review", {}).get("user_verified") is not True:
            raise ResumeBuildError(
                f"Selected evidence is not currently verified: {current.get('title', evidence_id)}. Re-run selection."
            )
        if selected_item.get("user_verified") is not True:
            raise ResumeBuildError(
                f"Selection report does not mark evidence as verified: {current.get('title', evidence_id)}"
            )

        # Reject stale reports if evidence content changed after selection.
        selected_source = selected_item.get("source", {})
        current_source = current.get("source", {})
        if selected_item.get("statement", "") != current.get("statement", ""):
            raise ResumeBuildError(
                f"Selection report is stale for '{current.get('title', evidence_id)}'; re-run evidence selection."
            )
        if selected_source.get("text", "") != current_source.get("text", ""):
            raise ResumeBuildError(
                f"Source evidence changed for '{current.get('title', evidence_id)}'; re-run evidence selection."
            )

        # Current store is the source of truth; selection report contributes ordering/reasons only.
        merged = dict(current)
        merged["score"] = selected_item.get("score", 0)
        merged["reason"] = selected_item.get("reason", [])
        merged["matched_required_skills"] = selected_item.get("matched_required_skills", [])
        merged["matched_preferred_skills"] = selected_item.get("matched_preferred_skills", [])
        validated.append(merged)

    # Education is a core resume section, not a JD keyword match. Include verified
    # education from the current store even when the selector assigned it no score.
    # This uses current source-backed evidence; it does not add or rewrite a claim.
    selected_ids = {item.get("evidence_id") for item in validated}
    for current in store.get("evidence", []):
        if current.get("category") != "education":
            continue
        if current.get("review", {}).get("user_verified") is not True:
            continue
        evidence_id = current.get("evidence_id")
        if not evidence_id or evidence_id in selected_ids:
            continue
        baseline = dict(current)
        baseline["score"] = 0
        baseline["reason"] = ["included as a core resume section: verified education"]
        baseline["included_as_core_section"] = True
        validated.append(baseline)
        selected_ids.add(evidence_id)

    # The master resume always has its summary and a full grouped skills section. Include them from the verified
    # store (like education above): skills the job asks for are listed first within their group by the layout.
    grouped_store = any(
        isinstance(item.get("metadata"), dict) and "print_group" in item["metadata"] for item in store.get("evidence", [])
    )
    for current in store.get("evidence", []):
        category = current.get("category")
        is_core_skill = category == "skill" and grouped_store and isinstance(current.get("metadata"), dict) and "print_group" in current["metadata"]
        # Credentials (certifications, achievements) are short and not job-specific: like the master, all verified ones print.
        if category not in {"summary", "certification", "achievement"} and not is_core_skill:
            continue
        if current.get("review", {}).get("user_verified") is not True:
            continue
        evidence_id = current.get("evidence_id")
        if not evidence_id or evidence_id in selected_ids:
            continue
        baseline = dict(current)
        baseline["score"] = 0
        baseline["reason"] = ["included as a core resume section: verified " + ("skill" if category == "skill" else str(category))]
        baseline["included_as_core_section"] = True
        validated.append(baseline)
        selected_ids.add(evidence_id)

    return validated


def _contact_lines(candidate: dict[str, Any]) -> list[str]:
    parts = [candidate.get("email"), candidate.get("phone"), candidate.get("location")]
    line1 = "  |  ".join(str(item).strip() for item in parts if item and str(item).strip())

    links = [candidate.get("linkedin"), candidate.get("github")]
    line2 = "  |  ".join(str(item).strip() for item in links if item and str(item).strip())
    return [line for line in (line1, line2) if line]


def _skills_text(records: list[dict[str, Any]]) -> str:
    # Use only the canonical title from each selected, verified skill record.
    return ", ".join(
        dict.fromkeys(
            str(item.get("title", "")).strip()
            for item in records
            if item.get("category") == "skill" and str(item.get("title", "")).strip()
        )
    )


def _render_education(document: Document, item: dict[str, Any]) -> None:
    metadata = item.get("metadata", {})
    title_parts = [metadata.get("degree"), metadata.get("field_of_study")]
    title = " — ".join(str(part).strip() for part in title_parts if part)
    if not title:
        title = str(item.get("title") or "Education")

    institution = metadata.get("institution")
    details: list[str] = []
    if institution:
        details.append(str(institution))
    if metadata.get("cgpa") is not None:
        details.append(f"CGPA: {metadata['cgpa']}")
    start_date, end_date = metadata.get("start_date"), metadata.get("end_date")
    if start_date or end_date:
        details.append(f"{start_date or ''} - {end_date or ''}".strip(" -"))
    if metadata.get("location"):
        details.append(str(metadata["location"]))

    _add_entry_heading(document, title, " | ".join(details) if details else None)


def _render_experience(document: Document, item: dict[str, Any]) -> None:
    metadata = item.get("metadata", {})
    role = metadata.get("role")
    company = metadata.get("company")
    title = " — ".join(str(x).strip() for x in (role, company) if x) or item.get("title", "Experience")
    start_date, end_date = metadata.get("start_date"), metadata.get("end_date")
    detail = f"{start_date or ''} - {end_date or ''}".strip(" -") or None
    if metadata.get("location"):
        detail = f"{detail} | {metadata['location']}" if detail else str(metadata["location"])
    _add_entry_heading(document, str(title), detail)

    bullets = metadata.get("bullets", [])
    if not isinstance(bullets, list):
        bullets = []
    for bullet in bullets:
        _add_bullet(document, str(bullet))

    if not bullets and item.get("statement"):
        _add_bullet(document, str(item["statement"]))


def _render_project(document: Document, item: dict[str, Any]) -> None:
    _add_entry_heading(document, str(item.get("title") or "Project"))
    metadata = item.get("metadata", {})
    bullets = metadata.get("bullets", [])
    if not isinstance(bullets, list):
        bullets = []
    if bullets:
        for bullet in bullets:
            _add_bullet(document, str(bullet))
    elif item.get("statement"):
        _add_bullet(document, str(item["statement"]))


def build_tailored_resume(
    selection: dict[str, Any],
    store: dict[str, Any],
    output_path: str | Path,
    *,
    audit_path: str | Path | None = None,
) -> Path:
    """Create an ATS-friendly DOCX using only currently verified evidence.

    The function does not rewrite bullets or invent a profile summary. It formats
    existing, verified evidence and rejects stale or unverified selection reports.
    """
    candidate = store.get("candidate")
    if not isinstance(candidate, dict) or not candidate.get("name"):
        raise ResumeBuildError("Evidence store has no candidate name.")

    from app.resume.tailoring_logic import tailor_for_job

    content = tailor_for_job(selection, store)
    records = content.records
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    document = _render_docx(build_layout(records, candidate, content.matches))

    document.core_properties.title = f"Tailored Resume - {selection.get('job', {}).get('title', 'Job Application')}"
    document.core_properties.subject = "Resume generated from user-verified evidence"
    document.core_properties.author = "JobPilot"
    document.save(output)

    if audit_path is not None:
        audit = {
            "generated_at_utc": _utc_now(),
            "output_file": output.name,
            "job": selection.get("job", {}),
            "source_resume": store.get("source_resume", {}),
            "evidence_count": len(records),
            "evidence": [
                {
                    "evidence_id": item.get("evidence_id"),
                    "category": item.get("category"),
                    "title": item.get("title"),
                    "source": item.get("source", {}),
                    "review_status": item.get("review", {}).get("status"),
                    "user_verified": item.get("review", {}).get("user_verified"),
                    "included_as_core_section": bool(item.get("included_as_core_section", False)),
                }
                for item in records
            ],
            "safety": {
                "only_currently_verified_evidence_used": True,
                "bullets_rewritten": False,
                "claims_generated": False,
            },
        }
        audit_file = Path(audit_path).expanduser().resolve()
        audit_file.parent.mkdir(parents=True, exist_ok=True)
        audit_file.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return output


def build_tailored_resume_from_files(
    selection_path: str | Path,
    store_path: str | Path,
    output_path: str | Path,
    *,
    audit_path: str | Path | None = None,
) -> Path:
    selection = _read_json(selection_path)
    store = _read_json(store_path)
    return build_tailored_resume(selection, store, output_path, audit_path=audit_path)


def default_output_path(job_title: str, directory: str | Path) -> Path:
    return Path(directory).expanduser() / f"Tailored_{_safe_slug(job_title)}.docx"


__all__ = [
    "ResumeBuildError",
    "build_tailored_resume",
    "build_tailored_resume_from_files",
    "default_output_path",
]
