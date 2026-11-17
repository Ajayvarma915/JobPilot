"""Tests for jobs held for review: stored by the sync, hidden from the normal list, decided by the user.

Uses a temporary database and a fake source. No network and no real data.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["JOBPILOT_DATABASE_PATH"] = str(Path(_TEMP_DIR.name) / "test_job_review.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.api import main as api_main  # noqa: E402
from app.db.database import Base, SessionLocal, engine  # noqa: E402
from app.db.models import Job, JobReview  # noqa: E402
from scripts import sync_target_companies as sync  # noqa: E402

STATED = "Minimum qualifications: 1 year of software development experience. Build backend services in Python."
UNSTATED = "Build backend services in Python and work with a friendly team on cloud systems every day."

COMPANY = {
    "id": "acme", "name": "Acme", "website": "https://acme.example", "careers_url": "https://acme.example/careers",
    "integration": {"provider": "lever", "status": "active", "verified": True, "settings": {"site": "acme"}},
}


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class FakeCollector:
    def __init__(self, jobs):
        self.jobs = jobs

    def collect(self):
        return [dict(job) for job in self.jobs]


def posting(key: str, description: str, title: str = "Software Engineer") -> dict:
    return {"external_id": key, "title": f"{title} {key}", "url": f"https://acme.example/{key}", "source": "lever:acme",
            "location": ["Pune, India"], "description": description}


def run_sync(jobs, company=COMPANY):
    original = sync._build_collector
    sync._build_collector = lambda c, **kwargs: FakeCollector(jobs)
    try:
        return sync.sync_company(company, dry_run=False, maximum_required_years=2.0)
    finally:
        sync._build_collector = original


def titles(client, scope):
    body = client.get("/api/jobs", params={"review_scope": scope, "location": "India", "limit": 100}).json()
    return {item["title"]: item for item in body["items"]}


def fresh_client() -> TestClient:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestClient(api_main.app)


def test_sync_stores_ambiguous_jobs_for_review() -> None:
    client = fresh_client()
    result = run_sync([posting("a1", STATED), posting("b1", UNSTATED)])
    check(result.inserted == 2 and result.stored_for_review == 1, f"both stored, one held: {result}")
    main, review = titles(client, "main"), titles(client, "review")
    check(list(main) == ["Software Engineer a1"], f"the normal list shows only the clean job: {list(main)}")
    check(list(review) == ["Software Engineer b1"], f"the review tab shows the held job: {list(review)}")
    held = review["Software Engineer b1"]["review"]
    check(held["status"] == "pending" and "minimum_experience_not_found_review" in held["flags"], held)
    check(held["reasons"] and "years of experience" in held["reasons"][0], f"reasons are readable: {held}")
    check(main["Software Engineer a1"]["review"] is None, "a clean job carries no review")
    stats = client.get("/api/dashboard/stats").json()
    check(stats["active_jobs"] == 1 and stats["needs_review_jobs"] == 1, f"dashboard counts split: {stats}")


def test_decisions_are_kept_across_syncs() -> None:
    client = fresh_client()
    run_sync([posting("a1", STATED), posting("b1", UNSTATED), posting("c1", UNSTATED)])
    session = SessionLocal()
    try:
        ids = {job.external_id: job.id for job in session.query(Job).all()}
    finally:
        session.close()

    check(client.post(f"/api/jobs/{ids['b1']}/review-decision", json={"decision": "accept"}).json()["review"]["status"] == "accepted", "accept")
    check(client.post(f"/api/jobs/{ids['c1']}/review-decision", json={"decision": "dismiss"}).json()["review"]["status"] == "dismissed", "dismiss")
    check(client.post(f"/api/jobs/{ids['a1']}/review-decision", json={"decision": "accept"}).status_code == 404, "a clean job has nothing to decide")
    check(client.post(f"/api/jobs/{ids['b1']}/review-decision", json={"decision": "nonsense"}).status_code == 422, "bad decision rejected")

    check(set(titles(client, "main")) == {"Software Engineer a1", "Software Engineer b1"}, "an accepted job joins the normal list")
    check(not titles(client, "review"), "nothing is left waiting")
    check(set(titles(client, "dismissed")) == {"Software Engineer c1"}, "a dismissed job is only in the dismissed tab")
    check("Software Engineer c1" not in titles(client, "main"), "a dismissed job is hidden from the normal list")

    run_sync([posting("a1", STATED), posting("b1", UNSTATED), posting("c1", UNSTATED)])  # the next sync must not undo decisions
    check(set(titles(client, "main")) == {"Software Engineer a1", "Software Engineer b1"}, "decisions survive the next sync")
    check(set(titles(client, "dismissed")) == {"Software Engineer c1"}, "dismissal survives the next sync")

    check(client.post(f"/api/jobs/{ids['c1']}/review-decision", json={"decision": "reset"}).json()["review"]["status"] == "pending", "reset")
    check(set(titles(client, "review")) == {"Software Engineer c1"}, "a reset job waits for review again")


def test_job_that_becomes_clear_leaves_the_queue_and_closed_jobs_still_close() -> None:
    client = fresh_client()
    run_sync([posting("b1", UNSTATED), posting("d1", STATED), posting("e1", STATED)])
    check(set(titles(client, "review")) == {"Software Engineer b1"}, "held at first")
    result = run_sync([posting("b1", STATED), posting("d1", STATED)])  # b1 now states its years; e1 is gone
    check(not titles(client, "review") and "Software Engineer b1" in titles(client, "main"), "once clear, it joins the normal list")
    check(result.removed == 1 and "Software Engineer e1" not in titles(client, "main"), f"removal detection still works: {result}")
    session = SessionLocal()
    try:
        check(session.query(JobReview).count() == 0, "no stale review rows remain")
    finally:
        session.close()


def test_unverified_sources_never_store_review_jobs() -> None:
    client = fresh_client()
    pending = {**COMPANY, "integration": {**COMPANY["integration"], "status": "awaiting_validation", "verified": False}}
    result = run_sync([posting("b1", UNSTATED)], pending)
    check(result.inserted == 0 and not titles(client, "review") and not titles(client, "main"), f"nothing is written: {result}")


TESTS = [
    ("Sync stores ambiguous jobs and the API separates them", test_sync_stores_ambiguous_jobs_for_review),
    ("Accept, dismiss and reset are kept across syncs", test_decisions_are_kept_across_syncs),
    ("A job that becomes clear leaves the queue; removal still works", test_job_that_becomes_clear_leaves_the_queue_and_closed_jobs_still_close),
    ("Unverified sources store nothing", test_unverified_sources_never_store_review_jobs),
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
    api_main.engine.dispose()
    _TEMP_DIR.cleanup()
    print(f"\nUnit tests: {len(TESTS) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
