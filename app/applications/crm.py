"""Outreach drafts for recruiters and referral contacts, and the interview preparation plan.

Both are deterministic and built only from verified facts. Nothing here sends a message: an
outreach draft is text for the user to review, edit and send themselves.
"""
from __future__ import annotations

from typing import Any

REFERRAL_STATUSES = ("none", "asked", "agreed", "declined", "submitted")
CONTACT_KINDS = ("recruiter", "referral", "other")


def build_outreach_draft(
    *,
    contact: dict[str, Any],
    facts: dict[str, str],
    job: dict[str, Any] | None,
    verified_skills: list[str],
) -> dict[str, Any]:
    """A short, polite message that states only facts the user verified."""
    name = str(contact.get("name") or "").strip()
    first = name.split()[0] if name else ""
    kind = contact.get("kind") or "recruiter"
    title = str((job or {}).get("title") or "").strip()
    company = str((job or {}).get("company") or contact.get("company_name") or "").strip()
    used: list[str] = []
    warnings: list[str] = []

    lines = [f"Hi {first}," if first else "Hello,", ""]
    about = ""
    if facts.get("current_title") and facts.get("current_employer"):
        about = f" I currently work as a {facts['current_title']} at {facts['current_employer']}."
        used += ["profile.current_title", "profile.current_employer"]

    if kind == "referral":
        target = f"the {title} role" if title else "an engineering role"
        at = f" at {company}" if company else ""
        lines.append(f"I hope you are well. I am interested in {target}{at} and would value a referral if you feel I am a good fit.{about}")
    else:
        target = f"the {title} position" if title else "software engineering roles"
        at = f" at {company}" if company else ""
        lines.append(f"I am writing about {target}{at}.{about}")

    skills = [s for s in verified_skills if s][:5]
    if skills:
        lines.append(f"My verified experience includes {', '.join(skills)}.")
        used.append("evidence.skills")
    else:
        warnings.append("No verified skills were available, so the draft makes no skill claims.")
    lines.append("I would be glad to share my resume and answer any questions. Thank you for your time.")
    lines.append("")
    if facts.get("contact_name"):
        lines += ["Best regards,", facts["contact_name"]]
        used.append("profile.contact_name")
    else:
        lines.append("Best regards,")
        warnings.append("Your name is not in your profile; add it before sending.")
    return {"body": "\n".join(lines), "facts_used": sorted(set(used)), "warnings": warnings}


_COMMON_BEHAVIOURAL = [
    "Tell me about a project you are proud of and what you personally built.",
    "Describe a time you had to learn a new technology quickly.",
    "Tell me about a bug that was hard to find and how you found it.",
    "Describe a disagreement with a teammate and how it was resolved.",
    "Tell me about a deadline you were at risk of missing and what you did.",
    "Why this company and why this role?",
]

_CODING = {
    "backend": ["Implement an LRU cache.", "Design and implement a rate limiter.", "Write a function to merge overlapping intervals."],
    "frontend": ["Implement a debounce function.", "Build a small to-do list component with filtering.", "Flatten a deeply nested array."],
    "full_stack": ["Implement a debounce function.", "Design the API and tables for a to-do app, then implement one endpoint.", "Write a function to merge overlapping intervals."],
    "data": ["Write SQL for the top 3 rows per group using a window function.", "Deduplicate a large list while keeping order.", "Implement a streaming word counter."],
    "cloud_devops": ["Parse a log file and report the top error codes.", "Write a script that retries a failing call with backoff.", "Implement a simple rate limiter."],
    "security": ["Validate and sanitise untrusted input for a login form.", "Implement a function to detect a brute-force pattern in login attempts.", "Parse a log file and flag suspicious IPs."],
    "default": ["Solve Two Sum and explain the complexity.", "Check balanced parentheses.", "Merge two sorted lists."],
}

_DESIGN = {
    "backend": ["Design a URL shortener.", "Design a notification service.", "Design an API rate limiter service."],
    "frontend": ["Design a typeahead search component.", "Design an infinite-scroll feed.", "Design a form with validation and autosave."],
    "full_stack": ["Design a URL shortener end to end.", "Design a simple chat application.", "Design a job-board with search."],
    "data": ["Design a pipeline that ingests events and serves daily metrics.", "Design a deduplication job for millions of records."],
    "cloud_devops": ["Design a CI/CD pipeline with rollbacks.", "Design monitoring and alerting for a web service."],
    "security": ["Design authentication and session handling for a web app.", "Design audit logging for sensitive actions."],
    "default": ["Design a URL shortener.", "Design a simple key-value store."],
}


def build_interview_plan(
    *,
    title: str,
    company: str | None,
    required_skills: list[str],
    missing_skills: list[str],
    role_family: str,
    stage: str,
) -> list[dict[str, str]]:
    """Practice questions and preparation tasks for one application. ``stage`` is its status."""
    family = role_family if role_family in _CODING else "default"
    items: list[dict[str, str]] = []

    for skill in required_skills[:8]:
        items.append({"category": "technical_questions",
                      "text": f"Explain {skill}: the core concepts, a typical problem you would solve with it, and the trade-offs."})
    for exercise in _CODING[family]:
        items.append({"category": "coding_exercises", "text": exercise})
    # Early in the process the assessment is usually coding; design rounds come with interviews.
    if stage != "assessment":
        for prompt in _DESIGN[family]:
            items.append({"category": "system_design", "text": prompt})
    for question in _COMMON_BEHAVIOURAL:
        items.append({"category": "behavioural", "text": question.replace("this company", company) if company else question})

    steps = [
        f"Read about {company}: what it builds, its engineering blog and recent news." if company else "Research the company's products and engineering blog.",
        f"Re-read the job description for {title} and list the 5 things it stresses most.",
        "Re-read your own resume and be ready to explain every bullet and project in depth.",
        "Prepare 3 questions to ask the interviewer.",
    ]
    for skill in missing_skills[:5]:
        steps.append(f"You have no verified experience with {skill}: review its basics and be honest about it, "
                     "while showing how you would learn it. Do not claim experience you do not have.")
    items += [{"category": "preparation_steps", "text": step} for step in steps]
    return items
