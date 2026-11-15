"""Tests for job change detection, version history and removal detection (temp DB only)."""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["JOBPILOT_DATABASE_PATH"] = str(Path(_TEMP_DIR.name) / "test_job_versions.db")

from sqlalchemy import select  # noqa: E402

from app.db.database import Base, SessionLocal, engine  # noqa: E402
from app.db.job_repository import (  # noqa: E402
    CREATED, REACTIVATED, UNCHANGED, UPDATED, JobRepository, content_hash,
)
from app.db.models import Job, JobVersion  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _data(external_id: str = "1", **overrides) -> dict:
    data = {
        "source": "lever:test", "external_id": external_id, "title": "Software Engineer",
        "location": ["Hyderabad, India"], "url": f"https://example.com/{external_id}",
        "description": "Minimum qualifications: 1 year of experience.", "employment_type": "Full-time",
    }
    data.update(overrides)
    return data


def _fresh():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    repo = JobRepository(session)
    company = repo.get_or_create_company("Test Co")
    return session, repo, company


def _versions(session, job):
    return session.scalars(select(JobVersion).where(JobVersion.job_id == job.id).order_by(JobVersion.version_no)).all()


def test_create_unchanged_updated() -> None:
    session, repo, company = _fresh()
    try:
        first = repo.upsert_job_detailed(company, _data())
        check(first.status == CREATED, "first upsert creates")
        again = repo.upsert_job_detailed(company, _data(description="Minimum qualifications:   1 year of experience.\n"))
        check(again.status == UNCHANGED, "whitespace-only differences are not a change")
        check(len(_versions(session, first.job)) == 1, "no version for an unchanged job")

        changed = repo.upsert_job_detailed(company, _data(description="Minimum qualifications: 4 years of experience."))
        check(changed.status == UPDATED and changed.changed_fields == ["description"], f"got {changed.status} {changed.changed_fields}")
        versions = _versions(session, first.job)
        check([v.change_type for v in versions] == ["created", "updated"], [v.change_type for v in versions])
        check("1 year" in versions[0].description and "4 years" in versions[1].description, "snapshots keep both states")
        check(versions[1].changed_fields == "description" and versions[0].content_hash != versions[1].content_hash, "hash/fields recorded")

        loc = repo.upsert_job_detailed(company, _data(description="Minimum qualifications: 4 years of experience.", location=["Pune, India"]))
        check(loc.changed_fields == ["location"], "location change detected")
        session.commit()
    finally:
        session.close()


def test_pre_existing_job_gets_a_baseline() -> None:
    session, repo, company = _fresh()
    try:
        old_seen = datetime.utcnow() - timedelta(days=9)
        job = Job(company_id=company.id, external_id="9", title="Backend Engineer", location="Pune", url="https://x/9",
                  description="old text", source="lever:test", first_seen_at=old_seen, last_seen_at=old_seen, is_active=True)
        session.add(job)
        session.flush()
        result = repo.upsert_job_detailed(company, _data("9", title="Backend Engineer", location=["Pune"], url="https://x/9", description="new text"))
        check(result.status == UPDATED, result.status)
        versions = _versions(session, job)
        check([v.change_type for v in versions] == ["baseline", "updated"], [v.change_type for v in versions])
        check(versions[0].description == "old text" and versions[1].description == "new text", "baseline holds the pre-change state")
        session.commit()
    finally:
        session.close()


def test_removal_and_reactivation() -> None:
    session, repo, company = _fresh()
    try:
        for i in ("1", "2", "3"):
            repo.upsert_job_detailed(company, _data(i))
        removed = repo.mark_missing_inactive(company, ["lever:test"], {"1"})
        check(sorted(j.external_id for j in removed) == ["2", "3"], "jobs absent from the source are marked removed")
        jobs = {j.external_id: j for j in session.scalars(select(Job)).all()}
        check(jobs["1"].is_active and not jobs["2"].is_active and not jobs["3"].is_active, "only absent jobs deactivated")
        check([v.change_type for v in _versions(session, jobs["2"])] == ["created", "removed"], "removal is recorded as a version")
        check(repo.active_job_count(company, ["lever:test"]) == 1, "active count reflects removals")
        check(repo.mark_missing_inactive(company, ["lever:test"], {"1"}) == [], "removing twice is a no-op")
        check(repo.mark_missing_inactive(company, ["other:source"], set()) == [], "other sources are never touched")

        back = repo.upsert_job_detailed(company, _data("2"))
        check(back.status == REACTIVATED and back.job.is_active, "a re-posted job is reactivated")
        check(_versions(session, back.job)[-1].change_type == "reactivated", "reactivation recorded")
        session.commit()
    finally:
        session.close()


def test_compatibility_wrapper_and_hash() -> None:
    session, repo, company = _fresh()
    try:
        job, created = repo.upsert_job(company, _data("7"))
        check(created is True and job.id, "wrapper returns (job, created=True)")
        job2, created2 = repo.upsert_job(company, _data("7"))
        check(created2 is False and job2.id == job.id, "wrapper returns created=False for an existing job")
        check(content_hash({"title": "A  b"}) == content_hash({"title": "A b"}), "hash ignores whitespace")
        check(content_hash({"title": "A"}) != content_hash({"title": "B"}), "hash differs for different content")
        session.commit()
    finally:
        session.close()


TESTS = [
    ("Create, unchanged and updated with version history", test_create_unchanged_updated),
    ("Jobs stored before versioning get a baseline", test_pre_existing_job_gets_a_baseline),
    ("Removal detection and reactivation", test_removal_and_reactivation),
    ("Backward-compatible upsert wrapper and hash", test_compatibility_wrapper_and_hash),
]


def main() -> int:
    failed = 0
    for name, test in TESTS:
        try:
            test()
            print(f"PASS - {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL - {name}: {type(exc).__name__}: {exc}")
    engine.dispose()
    _TEMP_DIR.cleanup()
    print(f"\nUnit tests: {len(TESTS) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
