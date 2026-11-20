"""Tests for confirming resume evidence in the app (made-up resume, temporary store)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["JOBPILOT_DATABASE_PATH"] = str(Path(_TEMP_DIR.name) / "test_evidence_review.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.api import main as api_main  # noqa: E402
from app.db.database import engine  # noqa: E402
from app.resume.evidence_store import MasterResumeEvidenceStore  # noqa: E402
from scripts.test_resume_parser_layouts import SAMPLE  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_review_flow() -> None:
    folder = Path(_TEMP_DIR.name)
    resume = folder / "resume.txt"
    resume.write_text(SAMPLE, encoding="utf-8")
    store_path = folder / "store.json"
    MasterResumeEvidenceStore(store_path).build_from_file(resume)
    original = api_main.EVIDENCE_STORE_PATH
    api_main.EVIDENCE_STORE_PATH = store_path
    try:
        client = TestClient(api_main.app)
        pending = client.get("/api/evidence/records").json()
        check(pending["verified_count"] == 0 and pending["pending_count"] == len(pending["items"]) > 5, pending["pending_count"])
        check(all(not item["verified"] and item["statement"] for item in pending["items"]), "nothing starts verified, every record has text")

        ids = [item["evidence_id"] for item in pending["items"][:2]]
        after = client.post("/api/evidence/review", json={"evidence_ids": ids}).json()
        check(after["verified_count"] == 2, after["verified_count"])
        check({i["evidence_id"] for i in client.get("/api/evidence/records", params={"review": "verified"}).json()["items"]} == set(ids), "verified filter")
        check(len(client.get("/api/evidence/records").json()["items"]) == pending["pending_count"] - 2, "pending shrinks")
        summary = client.get("/api/evidence/summary").json()
        check(summary["verified_count"] == 2, "the summary agrees")

        withdrawn = client.post("/api/evidence/review", json={"evidence_ids": ids[:1], "verified": False}).json()
        check(withdrawn["verified_count"] == 1, "confirmation can be withdrawn")
        check(client.post("/api/evidence/review", json={"evidence_ids": ["nope"]}).status_code == 404, "unknown ids are refused")
        check(client.post("/api/evidence/review", json={"evidence_ids": []}).status_code == 422, "an empty list is refused")

        # a rebuild from the same resume keeps what you confirmed
        MasterResumeEvidenceStore(store_path).build_from_file(resume)
        check(client.get("/api/evidence/records", params={"review": "verified"}).json()["verified_count"] == 1, "rebuilding keeps confirmations")
    finally:
        api_main.EVIDENCE_STORE_PATH = original


TESTS = [("Records are listed, confirmed, withdrawn and survive a rebuild", test_review_flow)]


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
