"""Job-specific cover letters built only from verified facts.

The letter is a plain template filled with: the real job title and company, the candidate's
profile facts (name, current role, experience as the user wrote it), skills that verified
evidence supports, and verbatim statements from verified project evidence. Anything the
evidence does not support is left out and reported in ``not_claimed``. No model is used,
so nothing can be invented; the user edits the draft freely (each edit is a new version).
"""
from __future__ import annotations

import re
from io import BytesIO
from typing import Any

from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

MAX_PROJECTS = 2
MAX_SENTENCE_CHARS = 260
_YEARS_TEXT = re.compile(r"^\s*[\d.]+\+?\s*(years?|yrs?|months?)?\s*$", re.IGNORECASE)


def _first_sentence(text: str) -> str:
    cleaned = " ".join(str(text or "").split())
    match = re.match(r"(.+?[.!?])(\s|$)", cleaned)
    sentence = match.group(1) if match else cleaned
    return sentence[:MAX_SENTENCE_CHARS].rstrip()


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def generate_cover_letter(
    *,
    job: dict[str, Any],
    facts: dict[str, str],
    selection: dict[str, Any] | None,
    required_skills: list[str],
) -> dict[str, Any]:
    """Return {body, facts_used, evidence_used, not_claimed, warnings}."""
    title = str(job.get("title") or "this").strip()
    company = str(job.get("company") or "").strip()
    used: list[str] = ["job.title"] + (["job.company"] if company else [])
    warnings: list[str] = []
    evidence_used: list[str] = []

    paragraphs: list[str] = []
    greeting = f"Dear Hiring Team at {company}," if company else "Dear Hiring Team,"

    intro = f"I am writing to apply for the {title} position" + (f" at {company}." if company else ".")
    role, employer = facts.get("current_title"), facts.get("current_employer")
    if role and employer:
        intro += f" I currently work as a {role} at {employer}"
        used += ["profile.current_title", "profile.current_employer"]
        years = facts.get("years_experience", "")
        if years and _YEARS_TEXT.match(years):
            duration = years.strip() if re.search(r"[a-z]", years, re.I) else f"{years.strip()} years"
            intro += f", with about {duration} of experience"
            used.append("profile.years_experience")
        elif years:
            warnings.append("Your experience text was not used because it is not a simple duration (for example '1 year').")
        intro += "."
    paragraphs.append(intro)

    verified_skills: dict[str, str] = {}
    projects: list[dict[str, Any]] = []
    if selection:
        for item in selection.get("selected_evidence", []):
            for skill in list(item.get("matched_required_skills") or []) + list(item.get("matched_preferred_skills") or []):
                verified_skills.setdefault(str(skill).casefold(), str(skill))
            if item.get("category") == "project" and len(projects) < MAX_PROJECTS and item.get("statement"):
                projects.append(item)
        for skill in (selection.get("coverage") or {}).get("verified_covered") or []:
            verified_skills.setdefault(str(skill).casefold(), str(skill))
    else:
        warnings.append("No verified resume evidence was available, so the letter makes no skill or project claims.")

    matched = [skill for skill in required_skills if skill.casefold() in verified_skills]
    not_claimed = [skill for skill in required_skills if skill.casefold() not in verified_skills]
    if matched:
        paragraphs.append(
            f"The role calls for {_join(required_skills[:6])}. I have verified, hands-on experience with {_join(matched[:6])}."
            if len(required_skills) > 1 or matched != required_skills
            else f"I have verified, hands-on experience with {_join(matched)}, which this role asks for."
        )
        used.append("evidence.skills")
    elif selection:
        warnings.append("None of the job's required skills matched your verified evidence, so no skill claim was made.")

    if projects:
        lines = []
        for project in projects:
            lines.append(f"{project.get('title')}: {_first_sentence(project['statement'])}")
            evidence_used.append(str(project.get("evidence_id")))
        paragraphs.append("Relevant work from my projects: " + " ".join(lines))

    paragraphs.append(
        "Thank you for considering my application."
        + (f" I would welcome the chance to discuss how I can contribute to {company}." if company else " I would welcome the chance to discuss it further.")
    )
    name = facts.get("contact_name")
    if name:
        used.append("profile.contact_name")
        signoff = f"Sincerely,\n{name}"
    else:
        signoff = "Sincerely,"
        warnings.append("Your name is not in your profile; add it before sending.")

    body = greeting + "\n\n" + "\n\n".join(paragraphs) + "\n\n" + signoff
    return {
        "body": body,
        "facts_used": sorted(set(used)),
        "evidence_used": evidence_used,
        "not_claimed": not_claimed,
        "warnings": warnings,
    }


def cover_letter_docx(body: str, title: str) -> bytes:
    document = Document()
    document.core_properties.title = title
    document.core_properties.author = "JobPilot"
    for block in body.split("\n\n"):
        paragraph = document.add_paragraph()
        for index, line in enumerate(block.split("\n")):
            if index:
                paragraph.add_run().add_break()
            paragraph.add_run(line)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def cover_letter_pdf(body: str, title: str) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm, topMargin=22 * mm,
                                 bottomMargin=22 * mm, title=title, author="JobPilot")
    style = ParagraphStyle("Body", parent=getSampleStyleSheet()["Normal"], fontName="Helvetica", fontSize=11, leading=15)
    story: list[Any] = []
    for block in body.split("\n\n"):
        escaped = block.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
        story.append(Paragraph(escaped, style))
        story.append(Spacer(1, 6 * mm))
    document.build(story)
    return buffer.getvalue()
