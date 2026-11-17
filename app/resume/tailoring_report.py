"""Tailoring report and fail-closed no-fabrication check for generated resumes.

The generator already copies bullets verbatim from evidence you verified. This module
adds two things on top:

- ``fabrication_check``: opens the finished DOCX and confirms that every bullet is text
  of a verified evidence record (selected for this job, or verified education). Any other
  bullet is a violation and the caller must discard the file.
- ``build_tailoring_report``: explains what was reused, which job keywords were aligned,
  what was selected or reordered, and what still needs your review.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from docx import Document


class FabricationError(ValueError):
    """The generated document contains text that is not backed by verified evidence."""


def _norm(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _verified_records(store: dict[str, Any], selection: dict[str, Any]) -> list[dict[str, Any]]:
    selected_ids = {item.get("evidence_id") for item in selection.get("selected_evidence", []) if item.get("evidence_id")}
    records = []
    for record in store.get("evidence", []):
        if (record.get("review") or {}).get("user_verified") is not True:
            continue
        if record.get("evidence_id") in selected_ids or record.get("category") == "education":
            records.append(record)
    return records


def allowed_bullet_texts(store: dict[str, Any], selection: dict[str, Any]) -> set[str]:
    allowed: set[str] = set()
    for record in _verified_records(store, selection):
        texts = [record.get("statement"), record.get("title")]
        bullets = (record.get("metadata") or {}).get("bullets")
        if isinstance(bullets, list):
            texts.extend(bullets)
        allowed.update(_norm(text) for text in texts if text)
    return allowed


def fabrication_check(docx_path: str | Path, store: dict[str, Any], selection: dict[str, Any]) -> dict[str, Any]:
    """Every list bullet in the DOCX must be text of a verified, selected (or core education) record."""
    allowed = allowed_bullet_texts(store, selection)
    document = Document(str(docx_path))
    bullets = [p.text.strip() for p in document.paragraphs if p.style.name == "List Bullet" and p.text.strip()]
    violations = [bullet for bullet in bullets if _norm(bullet) not in allowed]
    return {"ok": not violations, "bullets_checked": len(bullets), "violations": violations[:20]}


def build_tailoring_report(selection: dict[str, Any], store: dict[str, Any]) -> dict[str, Any]:
    selected = list(selection.get("selected_evidence", []))
    coverage = selection.get("coverage") or {}

    reused: list[dict[str, Any]] = []
    keywords: dict[str, str] = {}
    for item in selected:
        matched = list(item.get("matched_required_skills") or []) + list(item.get("matched_preferred_skills") or []) \
            + list(item.get("matched_job_technologies") or [])
        for word in matched:
            keywords.setdefault(_norm(word), str(word))
        source = item.get("source") or {}
        reused.append({
            "evidence_id": item.get("evidence_id"),
            "category": item.get("category"),
            "title": item.get("title"),
            "source_file": source.get("file"),
            "source_section": source.get("section"),
            "matched_keywords": sorted({str(w) for w in matched}, key=str.casefold),
            "why_selected": list(item.get("reason") or []),
            "added_by_you": bool(item.get("user_confirmed")),
        })
    selected_ids = {item.get("evidence_id") for item in selected}
    for record in store.get("evidence", []):
        if record.get("category") == "education" and (record.get("review") or {}).get("user_verified") is True \
                and record.get("evidence_id") not in selected_ids:
            source = record.get("source") or {}
            reused.append({
                "evidence_id": record.get("evidence_id"), "category": "education", "title": record.get("title"),
                "source_file": source.get("file"), "source_section": source.get("section"),
                "matched_keywords": [], "why_selected": ["Included as a core section: verified education"],
            })

    by_category: dict[str, int] = {}
    for entry in reused:
        by_category[str(entry["category"])] = by_category.get(str(entry["category"]), 0) + 1

    needs_review: list[dict[str, Any]] = []
    for item in selection.get("review_queue", []):
        needs_review.append({
            "kind": "unverified_evidence",
            "evidence_id": item.get("evidence_id"),
            "title": item.get("title"),
            "matched_required_skills": list(item.get("matched_required_skills") or []),
            "why": "Relevant to this job but not verified by you, so it was NOT included. Verify it in the evidence review if it is true.",
        })
    for skill in coverage.get("not_found_in_evidence") or []:
        needs_review.append({
            "kind": "uncovered_required_skill",
            "skill": skill,
            "why": "No evidence for this required skill in your resume. Do not claim it unless it is true; add real evidence to your master resume if you have it.",
        })

    added_by_you = [str(entry["title"]) for entry in reused if entry.get("added_by_you")]
    return {
        "job_title": (selection.get("job") or {}).get("title"),
        "added_by_you": added_by_you,
        "added_by_you_note": ("These were not in your verified resume evidence. You confirmed them for this resume only; "
                              "be ready to discuss each one honestly. Your master resume was not changed.") if added_by_you else None,
        "evidence_reused": reused,
        "keywords_aligned": sorted(keywords.values(), key=str.casefold),
        "required_skills": {
            "total": coverage.get("required_skills", 0),
            "covered_with_verified_evidence": list(coverage.get("verified_covered") or []),
            "awaiting_your_review": list(coverage.get("awaiting_evidence_review") or []),
            "no_evidence_found": list(coverage.get("not_found_in_evidence") or []),
        },
        "sections_changed": [
            {"section": category, "items_included": count,
             "change": "Selected and ordered for this job; each item's text is copied unchanged from your resume."}
            for category, count in sorted(by_category.items())
        ],
        "needs_review": needs_review,
        "wording": {"bullets_rewritten": False, "claims_generated": False},
        "original_resume": {
            "modified": False,
            "note": "Generating a tailored resume never changes your master resume or your evidence store.",
        },
    }
