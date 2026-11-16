"""Reusable employer-question answers built only from verified facts.

An answer is created from the candidate's saved profile facts and verified resume evidence.
Missing facts are never filled in: the answer is marked ``needs_input`` and says what to add.
Sensitive answers (salary, work authorization) and company-specific ones (why this company)
can only be approved with an explicit confirmation, and never while a placeholder remains.
"""
from __future__ import annotations

import re
from typing import Any

NEEDS_INPUT = "needs_input"
DRAFT = "draft"
APPROVED = "approved"

QUESTION_KEYS = (
    "why_company", "why_role", "challenging_project", "salary_expectation", "notice_period",
    "technology_experience", "work_authorization", "other",
)

_PLACEHOLDER = re.compile(r"\[[^\]]+\]")

_CLASSIFIERS = (
    ("salary_expectation", re.compile(r"\b(salary|compensation|ctc|pay expectation|expected pay)\b", re.I)),
    ("notice_period", re.compile(r"\bnotice period|how soon can you (join|start)|earliest start", re.I)),
    ("work_authorization", re.compile(r"\b(work authori[sz]ation|authori[sz]ed to work|right to work|visa|sponsorship)\b", re.I)),
    ("challenging_project", re.compile(r"\b(challenging|difficult|proud|most significant).{0,40}\b(project|problem|work)\b|\btell us about a project", re.I)),
    ("technology_experience", re.compile(r"\bexperience (with|in|using)\b|\bhow many years\b|\bproficien", re.I)),
    ("why_company", re.compile(r"\bwhy .{0,30}(join|work (for|at|with)|us|this company)|\bwhat attracts you to\b", re.I)),
    ("why_role", re.compile(r"\bwhy .{0,30}(role|position|job)|\binterested in this (role|position)", re.I)),
)

SENSITIVE_KEYS = {"salary_expectation", "work_authorization"}
COMPANY_SPECIFIC_KEYS = {"why_company", "why_role"}


def classify_question(question: str) -> str:
    for key, pattern in _CLASSIFIERS:
        if pattern.search(question or ""):
            return key
    return "other"


def unresolved_placeholders(answer: str) -> list[str]:
    return _PLACEHOLDER.findall(answer or "")


def _first_sentence(text: str, limit: int = 300) -> str:
    cleaned = " ".join(str(text or "").split())
    match = re.match(r"(.+?[.!?])(\s|$)", cleaned)
    return (match.group(1) if match else cleaned)[:limit].rstrip()


def _needs(key: str, message: str) -> dict[str, Any]:
    return {"answer": "", "status": NEEDS_INPUT, "facts_used": [], "message": message,
            "sensitive": key in SENSITIVE_KEYS, "company_specific": key in COMPANY_SPECIFIC_KEYS}


def draft_answer(
    question_key: str,
    *,
    facts: dict[str, str],
    job: dict[str, Any] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    technology: str | None = None,
    matched_skills: list[str] | None = None,
) -> dict[str, Any]:
    """Build a draft for one question. ``evidence`` must be VERIFIED evidence records only."""
    evidence = evidence or []
    job = job or {}
    title, company = str(job.get("title") or "").strip(), str(job.get("company") or "").strip()
    sensitive = question_key in SENSITIVE_KEYS
    company_specific = question_key in COMPANY_SPECIFIC_KEYS

    def result(answer: str, status: str, used: list[str], message: str | None = None) -> dict[str, Any]:
        return {"answer": answer, "status": status, "facts_used": used, "message": message,
                "sensitive": sensitive, "company_specific": company_specific}

    if question_key == "salary_expectation":
        value = facts.get("salary_expectation")
        if not value:
            return _needs(question_key, "Enter your salary expectation in an application's preparation form first. JobPilot never guesses a number.")
        return result(f"My expected compensation is {value}.", DRAFT, ["profile.salary_expectation"])

    if question_key == "notice_period":
        value = facts.get("notice_period")
        if not value:
            return _needs(question_key, "Add your notice period to your candidate profile.")
        return result(f"My notice period is {value}.", DRAFT, ["profile.notice_period"])

    if question_key == "work_authorization":
        value = facts.get("work_authorization")
        if not value:
            return _needs(question_key, "Add your work authorization to your candidate profile.")
        text = f"My work authorization status: {value}."
        used = ["profile.work_authorization"]
        sponsorship = (facts.get("requires_sponsorship") or "").lower()
        if sponsorship in {"yes", "no"}:
            text += " I " + ("do" if sponsorship == "yes" else "do not") + " require visa sponsorship."
            used.append("profile.requires_sponsorship")
        return result(text, DRAFT, used)

    if question_key == "technology_experience":
        tech = (technology or "").strip()
        if not tech:
            return _needs(question_key, "Say which technology the question asks about.")
        pattern = re.compile(r"(?<![\w+#.])" + re.escape(tech) + r"(?![\w+#])", re.IGNORECASE)
        for record in evidence:
            haystack = " ".join([str(record.get("title") or ""), str(record.get("statement") or ""),
                                 " ".join(str(b) for b in (record.get("metadata") or {}).get("bullets", []) or [])])
            if pattern.search(haystack):
                title_text = str(record.get("title") or "my work")
                return result(f"I have used {tech} in {title_text}: {_first_sentence(record.get('statement') or '')}",
                              DRAFT, [f"evidence.{record.get('evidence_id')}"])
        return _needs(question_key, f"No verified evidence of {tech} was found. Do not claim it unless it is true; add real evidence to your master resume first.")

    if question_key == "challenging_project":
        for record in evidence:
            if record.get("category") == "project" and record.get("statement"):
                return result(f"One project I am proud of is {record.get('title')}. {_first_sentence(record['statement'])}",
                              DRAFT, [f"evidence.{record.get('evidence_id')}"])
        return _needs(question_key, "No verified project evidence was found. Verify a project in your resume evidence first.")

    if question_key in COMPANY_SPECIFIC_KEYS:
        where = f" at {company}" if company else ""
        opening = f"I am interested in the {title or 'role'}{where}."
        used = ["job.title"] + (["job.company"] if company else [])
        skills = [s for s in (matched_skills or []) if s]
        if skills:
            opening += f" I bring verified experience with {', '.join(skills[:5])}."
            used.append("evidence.skills")
        placeholder = f"[Add what specifically draws you to {company or 'this company'}]"
        return result(f"{opening} {placeholder}", NEEDS_INPUT, used,
                      "Only you can say why this company interests you. Replace the bracketed part, then approve.")

    return _needs("other", "JobPilot cannot answer this from verified facts. Write your own answer, then approve it.")


def approval_blockers(*, answer: str, sensitive: bool, company_specific: bool, confirm: bool) -> list[str]:
    blockers: list[str] = []
    if not (answer or "").strip():
        blockers.append("The answer is empty.")
    placeholders = unresolved_placeholders(answer)
    if placeholders:
        blockers.append("Replace the placeholder(s) first: " + ", ".join(placeholders))
    if (sensitive or company_specific) and not confirm:
        reason = "sensitive" if sensitive else "company-specific"
        blockers.append(f"This answer is {reason}; approve it with an explicit confirmation.")
    return blockers
