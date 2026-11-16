"""Lifecycle rules for applications: readiness, applied timestamp, duplicates, history (temp DB)."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

_TEMP_DIR = tempfile.TemporaryDirectory()
DB_PATH = Path(_TEMP_DIR.name) / "test_application_lifecycle.db"
os.environ["JOBPILOT_DATABASE_PATH"] = str(DB_PATH)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.api import main as api_main  # noqa: E402
from app.applications import tracker  # noqa: E402
from app.db.database import Base, SessionLocal, engine  # noqa: E402
from app.db.job_repository import JobRepository  # noqa: E402
from app.db.models import Job  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _history(client: TestClient, application_id: int) -> list[tuple[str | None, str]]:
    items = client.get(f"/api/applications/{application_id}/history").json()["items"]
    return [(item["from_status"], item["to_status"]) for item in items]


def test_lifecycle_rules_and_history() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        repo = JobRepository(session)
        company = repo.get_or_create_company("Acme")
        job_id = repo.upsert_job_detailed(company, {"source": "lever:acme", "external_id": "1", "title": "Backend Engineer",
                                                    "location": ["Pune, India"], "url": "https://acme.example/1",
                                                    "description": "Minimum qualifications: 1 year of experience with Java. " + "You will design and build backend services, review code, and work with product teams to ship reliable features. " * 6}).job.id
        session.commit()
    finally:
        session.close()

    generated = Path(_TEMP_DIR.name) / "generated"
    generated.mkdir()
    (generated / "Tailored_Backend_20261116T000000Z.docx").write_bytes(b"docx")
    original_dir = tracker.GENERATED_RESUMES_DIR
    tracker.GENERATED_RESUMES_DIR = generated
    client = TestClient(api_main.app)
    try:
        created = client.post("/api/applications", json={"job_id": job_id})
        check(created.status_code == 201, created.text)
        application = created.json()
        app_id = application["id"]
        check(application["status"] == "saved" and application["applied_at"] is None, "a new entry is just saved, never applied")
        check(client.post("/api/applications", json={"job_id": job_id}).status_code == 409, "a job can be tracked only once")
        check(client.post("/api/applications", json={"job_id": 9999}).status_code in {404, 409, 422}, "unknown job refused")

        # Saved / preparing never count as applied.
        check(client.patch(f"/api/applications/{app_id}", json={"status": "preparing"}).json()["applied_at"] is None, "preparing has no applied_at")

        # ready_to_apply needs the checklist, and even then it is NOT applied.
        blocked = client.patch(f"/api/applications/{app_id}", json={"status": "ready_to_apply"})
        check(blocked.status_code == 409 and blocked.json()["detail"]["blockers"], f"checklist blocks ready_to_apply: {blocked.text}")
        ready = client.patch(f"/api/applications/{app_id}", json={
            "status": "ready_to_apply", "resume_filename": "Tailored_Backend_20261116T000000Z.docx", "job_reviewed": True,
            "eligibility_confirmed": True, "resume_reviewed": True, "application_details_reviewed": True})
        check(ready.status_code == 200 and ready.json()["status"] == "ready_to_apply", ready.text)
        check(ready.json()["applied_at"] is None, "ready_to_apply must NOT create an applied timestamp")

        # Only the explicit status change records the submission time.
        applied = client.patch(f"/api/applications/{app_id}", json={"status": "applied"}).json()
        check(applied["status"] == "applied" and applied["applied_at"], "the confirmed submission sets applied_at")
        stamp = applied["applied_at"]
        interview = client.patch(f"/api/applications/{app_id}", json={"status": "interview", "next_action": "Prepare", "follow_up_date": "2026-12-01"}).json()
        check(interview["applied_at"] == stamp and interview["next_action"] == "Prepare" and interview["follow_up_date"] == "2026-12-01",
              "later statuses keep the original applied_at; next action and follow-up are stored")

        check(_history(client, app_id) == [(None, "saved"), ("saved", "preparing"), ("preparing", "ready_to_apply"),
                                          ("ready_to_apply", "applied"), ("applied", "interview")], _history(client, app_id))

        # A change made outside the API (as the email-review approval does) is still recorded.
        connection = sqlite3.connect(str(DB_PATH))
        connection.execute("UPDATE applications SET status = 'offer' WHERE id = ?", (app_id,))
        connection.commit()
        connection.close()
        check(_history(client, app_id)[-1] == ("interview", "offer"), "direct database changes are recorded by the trigger")

        # Applications that existed before history tracking get a starting row.
        connection = sqlite3.connect(str(DB_PATH))
        connection.executescript("DROP TRIGGER trg_application_status_insert; DROP TRIGGER trg_application_status_update; DROP TABLE application_status_history;")
        connection.commit()
        connection.close()
        again = client.get(f"/api/applications/{app_id}/history")
        check(again.status_code == 200 and [i["to_status"] for i in again.json()["items"]] == ["offer"], f"backfilled: {again.text}")
        client.patch(f"/api/applications/{app_id}", json={"status": "rejected"})
        check(_history(client, app_id)[-1] == ("offer", "rejected"), "triggers are recreated and recording again")
        check(client.get("/api/applications/9999/history").status_code == 404, "unknown application -> 404")

        # Removing the tracker entry never deletes the job itself.
        check(client.delete(f"/api/applications/{app_id}").status_code == 200, "entry removed")
        session = SessionLocal()
        try:
            check(session.scalar(select(Job).where(Job.id == job_id)) is not None, "the source job survives removal of its tracker entry")
        finally:
            session.close()
        check(client.get(f"/api/applications/{app_id}").status_code == 404, "the entry is gone")
    finally:
        tracker.GENERATED_RESUMES_DIR = original_dir


TESTS = [("Readiness, applied timestamp, duplicates, history and removal", test_lifecycle_rules_and_history)]


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
