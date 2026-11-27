"""Tests for the in-app job update runner (harmless fake commands, no network)."""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["JOBPILOT_DATABASE_PATH"] = str(Path(_TEMP_DIR.name) / "test_sync_runner.db")
os.environ["JOBPILOT_BACKUP_DIR"] = str(Path(_TEMP_DIR.name) / "backups")  # never the real backups folder

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


def test_backup_runs_before_the_steps() -> None:
    import io
    import json
    import sqlite3
    from contextlib import redirect_stdout

    from scripts import run_job_update

    live = Path(_TEMP_DIR.name) / "live_for_backup.db"
    connection = sqlite3.connect(live)
    connection.execute("CREATE TABLE t (x INTEGER)")
    connection.execute("INSERT INTO t VALUES (1)")
    connection.commit()
    connection.close()
    backups = Path(_TEMP_DIR.name) / "backups_for_update"
    saved = run_job_update.backup_first(live, backups)
    check(saved is not None and saved.is_file() and saved.parent == backups, "a backup file is written")
    copy = sqlite3.connect(saved)
    try:
        check(copy.execute("SELECT x FROM t").fetchone() == (1,), "and it holds the data")
    finally:
        copy.close()  # an open handle blocks deleting the temporary folder on Windows
    check(run_job_update.backup_first(Path(_TEMP_DIR.name) / "missing.db", backups) is None, "a missing database is skipped, not fatal")

    # the update itself backs up first (default location is patched to the temp folder), then runs the steps
    steps = Path(_TEMP_DIR.name) / "steps_backup.json"
    steps.write_text(json.dumps([["Only step", ["-c", "print('Updated records       : 1')"]]]), encoding="utf-8")
    original = run_job_update.backup_first
    run_job_update.backup_first = lambda source=None, directory=None: original(live, backups)
    try:
        out = io.StringIO()
        with redirect_stdout(out):
            code = run_job_update.main(["prog", str(steps)])
    finally:
        run_job_update.backup_first = original
    text = out.getvalue()
    check(code == 0 and text.index("Database backup") < text.index("=== STEP Only step ===") < text.index("=== DONE ==="), text)


def test_second_start_while_running_is_refused() -> None:
    sync_runner.STEPS[:] = [("Slow step", ["-c", "import time; time.sleep(1.5)"])]
    client = TestClient(api_main.app)
    check(client.post("/api/sync/start").status_code == 202, "first start")
    check(client.post("/api/sync/start").status_code == 409, "second start while running -> 409")
    wait_until_done(client)


def test_daily_run_keeps_history_and_never_overlaps_the_button() -> None:
    from scripts import run_daily_update

    history = Path(_TEMP_DIR.name) / "daily_history.log"
    client = TestClient(api_main.app)
    # A warning on stderr and a title Windows' default code page cannot print must not stop the update.
    noisy = "import sys; print('a warning', file=sys.stderr); print('Remote \\U0001F30D Engineer'); print('Updated records       : 3')"
    sync_runner.STEPS[:] = [("Only step", ["-c", noisy])]
    check(run_daily_update.main(history) == 0, "a finished run succeeds")
    text_ = history.read_text(encoding="utf-8")
    check("a warning" in text_ and "\U0001F30D" in text_ and "result: finished" in text_, text_)
    check(client.get("/api/sync/status").json()["state"] == "finished", "the app sees the scheduled run")

    sync_runner.STEPS[:] = [("Broken step", ["-c", "import sys; sys.exit(2)"])]
    check(run_daily_update.main(history) == 1, "a failed step makes the scheduled run fail")
    check(history.read_text(encoding="utf-8").count("daily update =====") == 2, "each run is added to the history")

    sync_runner.STEPS[:] = [("Slow step", ["-c", "import time; time.sleep(1.5)"])]
    check(client.post("/api/sync/start").status_code == 202, "the button starts an update")
    check(run_daily_update.main(history) == 0, "the scheduled run steps aside")
    check("Skipped: an update was already running." in history.read_text(encoding="utf-8"), "and says so")
    wait_until_done(client)


def test_a_dropped_connection_is_waited_for_and_the_step_retried() -> None:
    """Regression: Wi-Fi dropped during a scheduled run and all seven remote boards failed."""
    import io
    from contextlib import redirect_stdout

    from scripts import run_job_update

    saved = (run_job_update.network_up, run_job_update.subprocess.call, run_job_update.time.sleep)
    run_job_update.time.sleep = lambda seconds: None
    try:
        def scenario(network: list[bool], exit_codes: list[int], args: list[str]) -> tuple[int, int, str]:
            calls: list[list[str]] = []
            answers = iter(network)
            codes = iter(exit_codes)
            run_job_update.network_up = lambda: next(answers)
            run_job_update.subprocess.call = lambda command: calls.append(command) or next(codes)
            out = io.StringIO()
            with redirect_stdout(out):
                code = run_job_update.run_step(args)
            return code, len(calls), out.getvalue()

        sync_args = ["-m", "scripts.sync_remote_boards"]
        # up at the start; the step fails and the network is down; down once more, then back
        code, runs, text_ = scenario([True, False, False, False, True], [1, 0], sync_args)
        check((code, runs) == (0, 2) and "=== RETRY ===" in text_, f"retried after the network returns: {code}, {runs}, {text_}")
        code, runs, text_ = scenario([True, True], [1], sync_args)
        check((code, runs) == (1, 1) and "RETRY" not in text_, "a failure with a working network is reported, not repeated")
        code, runs, _ = scenario([], [1], ["-m", "scripts.score_jobs"])
        check((code, runs) == (1, 1), "a step that does not read job sites never waits for the network")
    finally:
        run_job_update.network_up, run_job_update.subprocess.call, run_job_update.time.sleep = saved

    sync_runner.LOG_FILE.write_text("\n".join([
        "=== STEP Remote job boards ===", "  FAILED: no connection", "Boards: 0 ok, 7 failed", "The connection dropped during this step.",
        "=== RETRY ===", "  success: raw=5", "Boards: 7 ok, 0 failed", "=== STEP Remote job boards EXIT 0 ===", "=== DONE ===", ""]),
        encoding="utf-8")
    steps, _, _ = sync_runner._parse_log(False)
    check(steps[0]["summary"] == ["Boards: 7 ok, 0 failed"] and steps[0]["sources_done"] == 1, f"only the retry is reported: {steps}")


TESTS = [
    ("Update runs its steps in order and reports the summary", test_update_runs_steps_in_order_and_reports),
    ("Progress is live and read from files", test_progress_is_live_and_survives_without_the_web_process),
    ("A stopped update is reported as interrupted", test_a_stopped_update_is_reported_as_interrupted),
    ("A database backup runs before the update steps", test_backup_runs_before_the_steps),
    ("A second start while running is refused", test_second_start_while_running_is_refused),
    ("The daily run keeps a history and never overlaps the button", test_daily_run_keeps_history_and_never_overlaps_the_button),
    ("A dropped connection is waited for and the step retried", test_a_dropped_connection_is_waited_for_and_the_step_retried),
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
