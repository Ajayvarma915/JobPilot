"""Jobs held for your review: which jobs they are, why, and how they are hidden or shown.

A job lands here when it passes the role and location rules but something is ambiguous, most often
that the posting does not state a minimum years of experience. Nothing is discarded: such a job is
stored, kept out of the normal list, and waits for your Accept or Dismiss. A decision you make is
never changed by a later sync.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.engine import Connection, Engine

from app.db.models import Job, JobReview

PENDING = "pending"
ACCEPTED = "accepted"
DISMISSED = "dismissed"
DECISIONS = {"accept": ACCEPTED, "dismiss": DISMISSED, "reset": PENDING}

FLAG_TEXT = {
    "minimum_experience_not_found_review": "The posting does not state a minimum years of experience, so check it fits you.",
    "possible_duplicate_posting_review": "Another posting at this company looks the same (same title, place and description).",
    "remote_country_eligibility_unverified": "It is remote, but the countries it can be worked from are not stated.",
    "broad_title_manual_review": "The title is broad, so the real level of the role is unclear.",
    "description_missing": "The source gave no description for this job.",
    "needs_review": "Something about this posting is ambiguous.",
}


def ensure_review_table(bind: Engine | Connection) -> None:
    JobReview.__table__.create(bind=bind, checkfirst=True)


def flags_of(review: JobReview | None) -> list[str]:
    return [flag for flag in (review.flags or "").split(";") if flag] if review else []


def describe(review: JobReview | None) -> dict | None:
    """The shape the API returns for a job's review state (None when it has none)."""
    if review is None:
        return None
    flags = flags_of(review)
    return {
        "status": review.status,
        "flags": flags,
        "reasons": [FLAG_TEXT.get(flag, flag.replace("_", " ")) for flag in flags],
        "decided_at": review.decided_at.isoformat() if review.decided_at else None,
    }


def not_hidden_clause():
    """SQL condition: the job is not waiting for review and was not dismissed."""
    held = select(JobReview.job_id).where(JobReview.status.in_((PENDING, DISMISSED)))
    return Job.id.not_in(held)


def scope_clause(scope: str):
    """SQL condition for a jobs tab: main (normal), review (waiting for you) or dismissed."""
    if scope == "review":
        return Job.id.in_(select(JobReview.job_id).where(JobReview.status == PENDING))
    if scope == "dismissed":
        return Job.id.in_(select(JobReview.job_id).where(JobReview.status == DISMISSED))
    return not_hidden_clause()
