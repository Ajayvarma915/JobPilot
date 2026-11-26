"""Jobs held for your review: which jobs they are, why, and how they are hidden or shown.

A job lands here when it passes the role and location rules but something is ambiguous, most often
that the posting does not state a minimum years of experience. Nothing is discarded: such a job is
stored, kept out of the normal list, and waits for your Accept or Dismiss. A decision you make is
never changed by a later sync.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import or_, select, true
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

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


# A job found by an update is listed only while updates keep confirming it.
UNCONFIRMED_AFTER_DAYS = 14
# "The latest update" is the time shared by at least this many jobs, so that re-checking a few single jobs
# by hand cannot make everything else look old.
_BULK_UPDATE_JOBS = 25
# Added by you, never refreshed by an update, so age says nothing about them.
_ADDED_BY_YOU = ("imported_link", "email_application")


def confirmed_clause(db: Session):
    """SQL condition: hide jobs no update has confirmed for a long time. Nothing is deleted or changed.

    Age is measured against the latest update, not today, so a pause in updating hides nothing.
    """
    latest = db.scalar(
        select(Job.last_seen_at)
        .where(Job.is_active.is_(True), Job.source.not_in(_ADDED_BY_YOU), Job.last_seen_at.is_not(None))
        .order_by(Job.last_seen_at.desc())
        .offset(_BULK_UPDATE_JOBS - 1)
        .limit(1)
    )
    if latest is None:
        return true()
    return or_(
        Job.source.in_(_ADDED_BY_YOU),
        Job.last_seen_at.is_(None),
        Job.last_seen_at >= latest - timedelta(days=UNCONFIRMED_AFTER_DAYS),
    )


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
    if scope == "remote":
        # Remote jobs keep their review chip and Accept/Dismiss, so only dismissed ones are hidden.
        return Job.id.not_in(select(JobReview.job_id).where(JobReview.status == DISMISSED))
    return not_hidden_clause()
