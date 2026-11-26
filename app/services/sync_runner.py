"""Run the job update from the app: every company source, then the remote job boards.

This starts the same two commands you would run by hand (a full company sync, which also closes jobs
that left a career page, and the remote board sync) in ONE detached process that writes a log file.
Because the process is detached and the progress lives in files, restarting the web server (for
example uvicorn --reload) neither stops the update nor loses its progress. Only these fixed commands
are ever run; nothing from a request reaches the command line.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone
from typing import Any

from app.db.database import PROJECT_ROOT

STEPS: list[tuple[str, list[str]]] = [
    ("Company career pages", ["-m", "scripts.sync_target_companies", "--mode", "full", "--concurrency", "3"]),
    ("Remote job boards", ["-m", "scripts.sync_remote_boards"]),
    ("Score new jobs", ["-m", "scripts.score_jobs"]),
]
SUMMARY_KEYS = ("Raw jobs collected", "Role/location candidates", "Eligible needing review", "New database records",
                "Updated records", "Removed from source", "Failed API sources", "Boards:")

DATA_DIR = PROJECT_ROOT / "data"
STATE_FILE = DATA_DIR / "job_update_state.json"
LOG_FILE = DATA_DIR / "job_update.log"
STEPS_FILE = DATA_DIR / "job_update_steps.json"

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"state": "idle"}


def _write_state(state: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state), encoding="utf-8")


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        # os.kill(pid, 0) would TERMINATE a process on Windows, so ask the task list instead.
        result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"], capture_output=True, text=True,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return f'"{pid}"' in result.stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _parse_log(running: bool) -> tuple[list[dict[str, Any]], str | None, str | None]:
    """Steps, the step in progress, and the latest progress line, all read from the log."""
    try:
        text = LOG_FILE.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], None, None
    steps: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    buffer: list[str] = []
    for line in text.splitlines():
        started = re.fullmatch(r"=== STEP (.+) ===", line.strip())
        ended = re.fullmatch(r"=== STEP (.+) EXIT (-?\d+) ===", line.strip())
        if ended and current is not None:
            summary = [ln.strip() for ln in buffer if any(ln.strip().startswith(key) for key in SUMMARY_KEYS)]
            ok = int(ended.group(2)) == 0
            current.update({"state": "done" if ok else "failed", "summary": summary,
                            "error": None if ok else ("Some sources failed; see the summary." if summary else f"The step stopped with exit code {ended.group(2)}.")})
            current = None
        elif started:
            current = {"name": started.group(1), "state": "running", "summary": [], "error": None, "sources_done": 0}
            steps.append(current)
            buffer = []
        elif current is not None:
            buffer.append(line)
            if re.match(r"^\s+(success|FAILED|dry_run)", line):
                current["sources_done"] += 1
    progress = None
    if current is not None and buffer:
        for line in reversed(buffer):
            if line.strip():
                progress = line.strip()[:160]
                break
    return steps, (current["name"] if current is not None and running else None), progress


def status() -> dict[str, Any]:
    with _lock:
        state = _read_state()
        if state.get("state") == "running" and not _pid_alive(state.get("pid")):
            # The update process has ended (finished, or was stopped): settle the state from its log.
            steps, _, _ = _parse_log(False)
            finished_ok = bool(steps) and all(step["state"] != "running" for step in steps) and \
                LOG_FILE.exists() and "=== DONE ===" in LOG_FILE.read_text(encoding="utf-8", errors="replace")
            failed = any(step["state"] == "failed" for step in steps) or not finished_ok
            state = {**state, "state": "failed" if failed else "finished", "finished_at": _now(),
                     "interrupted": not finished_ok}
            _write_state(state)
        running = state.get("state") == "running"
        steps, current, progress = _parse_log(running) if state.get("state") != "idle" else ([], None, None)
        return {"state": state.get("state", "idle"), "started_at": state.get("started_at"), "finished_at": state.get("finished_at"),
                "interrupted": bool(state.get("interrupted")), "steps": steps, "current": current, "progress": progress if running else None}


def start() -> bool:
    """Start an update unless one is already running. Returns False when one is running."""
    with _lock:
        state = _read_state()
        if state.get("state") == "running" and _pid_alive(state.get("pid")):
            return False
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        STEPS_FILE.write_text(json.dumps(STEPS), encoding="utf-8")
        log = open(LOG_FILE, "w", encoding="utf-8")  # noqa: SIM115 - handed to the child process
        flags = 0
        if os.name == "nt":
            flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | \
                getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen([sys.executable, "-u", "-m", "scripts.run_job_update", str(STEPS_FILE)], cwd=str(PROJECT_ROOT),
                                   stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=flags,
                                   start_new_session=(os.name != "nt"))
        log.close()
        _write_state({"state": "running", "pid": process.pid, "started_at": _now(), "finished_at": None})
        return True
