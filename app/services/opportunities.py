"""Opportunity scoring, next-action advice and skill-gap analysis.

Everything here is deterministic and computed from data JobPilot actually holds. The rule-based match
and eligibility are authoritative: they decide whether a job is worth applying to; the extra
signals (freshness, company priority, disclosed pay) only rank jobs that are already viable.

Not modelled, because the data is not collected: application deadlines and competition indicators.
Undisclosed pay is neutral, never a penalty.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

APPLY_NOW = "apply_now"
REVIEW_FIRST = "review_first"
PREPARE_MISSING_SKILLS = "prepare_missing_skills"
SKIP = "skip"
ACTIONS = (APPLY_NOW, REVIEW_FIRST, PREPARE_MISSING_SKILLS, SKIP)

ACTION_LABELS = {
    APPLY_NOW: "Apply now",
    REVIEW_FIRST: "Review first",
    PREPARE_MISSING_SKILLS: "Prepare missing skills",
    SKIP: "Skip",
}

# Weights of the opportunity score (sum 100).
WEIGHTS = {"fit": 60.0, "freshness": 15.0, "company": 15.0, "compensation": 10.0}

SMALL_SAMPLE = 10


def freshness_points(posted_at: datetime | None, first_seen_at: datetime | None, now: datetime) -> tuple[float, str]:
    reference = posted_at or first_seen_at
    if reference is None:
        return 40.0, "Posting date unknown"
    days = max(0, (now - reference).days)
    label = "posted" if posted_at else "first seen"
    if days <= 3:
        return 100.0, f"Fresh: {label} {days} day(s) ago"
    if days <= 14:
        return 80.0, f"Recent: {label} {days} days ago"
    if days <= 30:
        return 50.0, f"{label.capitalize()} {days} days ago"
    if days <= 60:
        return 25.0, f"Getting old: {label} {days} days ago"
    return 0.0, f"Old: {label} {days} days ago"


def company_points(priority: int | None) -> tuple[float, str]:
    if priority == 1:
        return 100.0, "Top-priority company in your registry"
    if priority == 2:
        return 70.0, "Priority-2 company in your registry"
    if priority == 3:
        return 40.0, "Additional company in your registry"
    return 40.0, "Company not ranked in the registry"


def compensation_points(compensation: dict[str, Any] | None) -> tuple[float, str]:
    """Pay is shown on each job for information only. Product companies pay in a similar range, so it
    never filters or re-ranks jobs (every job gets the same neutral points)."""
    return 50.0, "Pay is shown for information only and does not affect ranking"


def decide_action(match: dict[str, Any]) -> tuple[str, list[str]]:
    """The authoritative next action, from the rule-based match only."""
    eligibility = match.get("eligibility") or {}
    mismatches = match.get("mismatches") or {}
    score = float(match.get("score") or 0)
    recommendation = match.get("recommendation")
    mandatory = list(mismatches.get("mandatory_requirement_mismatch") or [])
    reasons: list[str] = []

    if eligibility.get("status") == "excluded":
        reasons.append("Excluded by the eligibility policy: " + ", ".join(eligibility.get("reasons") or ["see job"]))
        return SKIP, reasons
    if recommendation == "low_match":
        reasons.append(f"Low overall match ({score:.0f}/100)")
        return SKIP, reasons
    if mandatory:
        reasons.extend(mandatory[:4])
        if score >= 45:
            reasons.append("Close enough to be worth preparing for")
            return PREPARE_MISSING_SKILLS, reasons
        reasons.append(f"Match is only {score:.0f}/100 with mandatory gaps")
        return SKIP, reasons
    if eligibility.get("status") == "eligible_needs_review":
        reasons.append("Eligibility needs a human check (for example experience or country not stated)")
        return REVIEW_FIRST, reasons
    if recommendation == "review":
        reasons.append(f"Borderline match ({score:.0f}/100)")
        return REVIEW_FIRST, reasons
    if mismatches.get("experience_mismatch"):
        reasons.extend(mismatches["experience_mismatch"][:2])
        return REVIEW_FIRST, reasons
    reasons.append(f"Strong rule-based fit ({score:.0f}/100) with no mandatory gaps")
    return APPLY_NOW, reasons


def score_opportunity(
    *,
    match: dict[str, Any],
    posted_at: datetime | None = None,
    first_seen_at: datetime | None = None,
    company_priority: int | None = None,
    compensation: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.utcnow()
    action, reasons = decide_action(match)
    fit = float(match.get("score") or 0)
    fresh, fresh_note = freshness_points(posted_at, first_seen_at, now)
    comp_company, company_note = company_points(company_priority)
    comp_pay, pay_note = compensation_points(compensation)
    components = {"fit": fit, "freshness": fresh, "company": comp_company, "compensation": comp_pay}
    total = sum(components[name] * WEIGHTS[name] / 100.0 for name in WEIGHTS)
    # A job the rules say to skip can never rank above one worth pursuing, whatever its extras.
    if action == SKIP:
        total = min(total, 30.0)
    return {
        "opportunity_score": round(total, 1),
        "action": action,
        "action_label": ACTION_LABELS[action],
        "reasons": reasons,
        "signals": [fresh_note, company_note, pay_note],
        "components": {name: round(value, 1) for name, value in components.items()},
        "weights": dict(WEIGHTS),
        "not_modelled": ["application deadline", "competition indicators"],
    }


def skill_gap_report(items: list[dict[str, Any]], *, top: int = 10) -> dict[str, Any]:
    """Which required skills are missing most often across the jobs worth pursuing.

    Uses only the jobs passed in (the real jobs in the database), counts, and says how many there were.
    """
    pursuing = [i for i in items if i.get("action") != SKIP]
    counts: Counter[str] = Counter()
    titles: dict[str, list[str]] = {}
    companies: dict[str, set[str]] = {}
    for item in pursuing:
        for skill in item.get("missing_required_skills") or []:
            counts[skill] += 1
            titles.setdefault(skill, [])
            if len(titles[skill]) < 3:
                titles[skill].append(item.get("title") or "")
            companies.setdefault(skill, set()).add(item.get("company") or "")
    n = len(pursuing)
    gaps = [
        {
            "skill": skill,
            "jobs_requiring": count,
            "share_of_jobs": round(count / n, 2) if n else 0.0,
            "example_titles": titles[skill],
            "companies": sorted(c for c in companies[skill] if c)[:5],
        }
        for skill, count in counts.most_common(top)
    ]
    plan = [
        {
            "skill": gap["skill"],
            "step": (f"Build one small, real project that uses {gap['skill']} and add it to your resume only once you have "
                     f"actually used it. It is a required skill in {gap['jobs_requiring']} of the {n} jobs you could pursue."),
        }
        for gap in gaps[:5]
    ]
    return {
        "jobs_considered": n,
        "small_sample": n < SMALL_SAMPLE,
        "note": (f"Based on only {n} job(s); treat the ranking as a hint, not a trend." if n < SMALL_SAMPLE
                 else f"Counted across {n} jobs currently stored for you; no external market data is used."),
        "gaps": gaps,
        "learning_plan": plan,
    }
