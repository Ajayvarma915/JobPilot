"""Adding an emailed application to the tracker against the REAL tables (not a cut-down test schema).

Regression: the first version failed with "NOT NULL constraint failed: jobs.created_at" on a real
database because the other email tests use a minimal schema that has no such column.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

_TEMP_DIR = tempfile.TemporaryDirectory()
DB_PATH = Path(_TEMP_DIR.name) / "real_schema.db"
os.environ["JOBPILOT_DATABASE_PATH"] = str(DB_PATH)

from fastapi.testclient import TestClient  # noqa: E402

from app.api import main as api_main  # noqa: E402
from app.db.database import Base, engine  # noqa: E402
from app.email import untracked  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_add_and_untrack_with_real_tables() -> None:
    Base.metadata.create_all(bind=engine)
    client = TestClient(api_main.app)
    check(client.get("/api/applications").status_code == 200, "creates the applications tables")
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    untracked.record_suggestion(
        connection, message_id="m-qualcomm", received_at="2026-11-17T13:07:00+00:00", sender="qualcomm@myworkday.com",
        subject="Successfully submitted application for Jane", snippet="",
        body_text="We have received your application for the position Associate Engineer - 3098178 . Our team is reviewing.",
    )
    connection.commit()
    connection.close()

    items = client.get("/api/email/suggestions").json()["items"]
    check([(i["company_guess"], i["title_guess"]) for i in items] == [("Qualcomm", "Associate Engineer")], items)
    added = client.post(f"/api/email/suggestions/{items[0]['id']}/add", json={"company": "Qualcomm", "title": "Associate Engineer"})
    check(added.status_code == 201, added.text)
    application = client.get(f"/api/applications/{added.json()['application_id']}").json()
    check((application["status"], application["job"]["company"], application["job"]["title"]) == ("applied", "Qualcomm", "Associate Engineer"), application)
    history = client.get(f"/api/applications/{application['id']}/history").json()["items"]
    check(history and history[-1]["to_status"] == "applied", f"status history is recorded: {history}")

    # the same job is not added twice, and the user can untrack it afterwards
    check(client.post(f"/api/email/suggestions/{items[0]['id']}/add", json={"company": "Qualcomm", "title": "x"}).status_code == 409, "no double add")
    check(client.delete(f"/api/applications/{application['id']}").status_code == 200, "untrack works")
    check(client.get("/api/applications").json()["total"] == 0, "nothing is left tracked")


TESTS = [("Adding an emailed application works on the real tables", test_add_and_untrack_with_real_tables)]


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
