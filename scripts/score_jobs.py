"""Score new and changed jobs after an update, so the first time you open the job list is quick.

    python -m scripts.score_jobs

The job list scores anything still missing a score before it shows a page (otherwise pages could repeat or
skip jobs). This does that work in advance.
"""
from __future__ import annotations

from sqlalchemy import select

from app.api.main import (
    JobMatcher, SessionLocal, _candidate_profile, _is_early_career_suitable, _is_target_software_role, _serialize_match, engine,
)
from app.db.models import Job
from app.services import job_review
from app.services.job_match_cache import ensure_match_cache_table, load_cached_matches, profile_fingerprint, save_cached_match


def score_missing(session_factory=SessionLocal, bind=engine) -> int:
    ensure_match_cache_table(bind)
    session = session_factory()
    try:
        jobs = [
            job for job in session.scalars(select(Job).where(Job.is_active.is_(True), job_review.confirmed_clause(session))).all()
            if _is_target_software_role(job.title) and _is_early_career_suitable(job.title, job.description or "")
        ]
        profile = _candidate_profile()
        profile_hash = profile_fingerprint(profile)
        cached = load_cached_matches(session, jobs, profile_hash)
        missing = [job for job in jobs if int(job.id) not in cached]
        if missing:
            matcher = JobMatcher(candidate_profile=profile)
            for job in missing:
                save_cached_match(session, job, profile_hash, _serialize_match(matcher.match(job)))
            session.commit()
        print(f"Scored {len(missing)} new or changed jobs ({len(jobs)} listed jobs in total).")
        return len(missing)
    finally:
        session.close()


if __name__ == "__main__":
    score_missing()
