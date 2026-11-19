"""Tests for the in-app job update runner (harmless fake commands, no network)."""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["JOBPILOT_DATABASE_PATH"] = str(Path(_TEMP_DIR.name) / "test_sync_runner.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.api import main as api_main  # noqa: E402
from app.db.database import engine  # noqa: E402
from app.services import sync_runner  # noqa: E402

# keep the runner's state and log files inside the temporary folder
sync_runner.DATA_DIR = Path(_TEMP_DIR.name)
sync_runner.STATE_FILE = Path(_TEMP_DIR.name) / "state.json"
sync_runner.LOG_FILE = Path(_TEMP_DIR.name) / "update.log"
sync_runner.STEPS_FILE = Path(_TEMP_DIR.name) / "steps.json"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def wait_until_done(client: TestClient) -> dict:
    for _ in range(300):
        state = client.get("/api/sync/status").json()
        if state["state"] != "running":
            return state
        time.sleep(0.1)
    raise AssertionError("the update never finished")


def test_update_runs_steps_in_order_and_reports() -> None:
    sync_runner.STEPS[:] = [
        ("First step", ["-c", "print('Raw jobs collected    : 12'); print('Removed from source   : 2'); print('noise')"]),
        ("Second step", ["-c", "import sys; print('Boards: 3 ok, 1 failed'); sys.exit(1)"]),
    ]
    client = TestClient(api_main.app)
    check(client.get("/api/sync/status").json()["state"] == "idle", "idle at first")
    started = client.post("/api/sync/start")
    check(started.status_code == 202, started.text)
    check(client.post("/api/sync/start").status_code in (202, 409), "a second start is refused while running")
    done = wait_until_done(client)
    names = [(s["name"], s["state"]) for s in done["steps"]]
    check(names == [("First step", "done"), ("Second step", "failed")], names)
    check(done["state"] == "failed" and done["finished_at"], done)
    check(done["steps"][0]["summary"] == ["Raw jobs collected    : 12", "Removed from source   : 2"], "only the summary lines are kept")
    check(done["steps"][1]["error"], "a failing step says so")
    check(done["interrupted"] is False, "a run that reached the end is not marked interrupted")

    sync_runner.STEPS[:] = [("Only step", ["-c", "print('Updated records       : 1')"])]
    client.post("/api/sync/start")
    again = wait_until_done(client)
    check(again["state"] == "finished" and again["steps"][0]["state"] == "done", f"it can run again after finishing: {again}")


def test_progress_is_live_and_survives_without_the_web_process() -> None:
    program = ";".join([
        "import time",
        "print('[Acme] lever: collecting...', flush=True)",
        "print('  success: raw=5, candidates=1', flush=True)",
        "print('[Beta] lever: collecting...', flush=True)",
        "time.sleep(2)",
    ])
    sync_runner.STEPS[:] = [("Company career pages", ["-c", program])]
    client = TestClient(api_main.app)
    check(client.post("/api/sync/start").status_code == 202, "start")
    seen = None
    for _ in range(40):
        state = client.get("/api/sync/status").json()
        if state["state"] == "running" and state["steps"] and state["steps"][0]["sources_done"] >= 1 and state["progress"]:
            seen = state
            break
        time.sleep(0.1)
    check(seen is not None, "progress appears while it runs")
    check(seen["steps"][0]["sources_done"] == 1 and "Beta" in seen["progress"], seen)
    # a new status reader (as after a web-server restart) sees the same running update from the files alone
    check(sync_runner.status()["state"] == "running", "the state comes from files, not memory")
    done = wait_until_done(client)
    check(done["state"] == "finished" and done["steps"][0]["sources_done"] == 1, done)


def test_a_stopped_update_is_reported_as_interrupted() -> None:
    sync_runner.STATE_FILE.write_text('{"state": "running", "pid": 999999, "started_at": "2026-11-19T00:00:00+00:00"}', encoding="utf-8")
    sync_runner.LOG_FILE.write_text("\n".join(["=== STEP First step ===", "  success: raw=1", ""]), encoding="utf-8")
    state = sync_runner.status()
    check(state["state"] == "failed" and state["interrupted"] is True, state)
    check(state["steps"][0]["state"] == "running", "the step that was in progress is shown as unfinished")


def test_second_start_while_running_is_refused() -> None:
    sync_runner.STEPS[:] = [("Slow step", ["-c", "import time; time.sleep(1.5)"])]
    client = TestClient(api_main.app)
    check(client.post("/api/sync/start").status_code == 202, "first start")
    check(client.post("/api/sync/start").status_code == 409, "second start while running -> 409")
    wait_until_done(client)


TESTS = [
    ("Update runs its steps in order and reports the summary", test_update_runs_steps_in_order_and_reports),
    ("Progress is live and read from files", test_progress_is_live_and_survives_without_the_web_process),
    ("A stopped update is reported as interrupted", test_a_stopped_update_is_reported_as_interrupted),
    ("A second start while running is refused", test_second_start_while_running_is_refused),
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
