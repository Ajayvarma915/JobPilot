"""Runs the job update: a database backup, then the update steps one after another, with progress markers.

Started by the app's "Update jobs now" button (app/services/sync_runner.py) as its own process, so a
restart of the web server does not stop it, and by the daily scheduled task (scripts/daily_update.ps1).

    python -m scripts.run_job_update                # the default steps (company pages, then remote boards)
    python -m scripts.run_job_update steps.json     # steps from a file: [[name, [python args...]], ...]
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

# Looked up (never contacted) to tell whether the network works: two unrelated services.
NETWORK_HOSTS = ("boards-api.greenhouse.io", "www.google.com")
NETWORK_WAIT_SECONDS = 600
NETWORK_PAUSE_SECONDS = 15


def network_up() -> bool:
    for host in NETWORK_HOSTS:
        try:
            socket.getaddrinfo(host, 443)
            return True
        except OSError:
            continue
    return False


def wait_for_network(timeout: float = NETWORK_WAIT_SECONDS, pause: float = NETWORK_PAUSE_SECONDS) -> bool:
    """Wait for the network, for example while Wi-Fi reconnects after the PC wakes. False if it never came."""
    if network_up():
        return True
    print(f"No network. Waiting up to {timeout / 60:g} minutes for it.", flush=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(pause)
        if network_up():
            print("The network is back.", flush=True)
            return True
    print("The network did not come back.", flush=True)
    return False


def run_step(args: list[str]) -> int:
    """Run one step. A step that reads job sites waits for the network, and is run once more if it
    failed because the connection dropped. Repeating a sync is safe."""
    reads_the_web = any(str(arg).startswith("scripts.sync_") for arg in args)
    if reads_the_web:
        wait_for_network()
    code = subprocess.call([sys.executable, "-u", *args])
    if code and reads_the_web and not network_up():
        print("The connection dropped during this step.", flush=True)
        if wait_for_network():
            print("=== RETRY ===", flush=True)
            code = subprocess.call([sys.executable, "-u", *args])
    return code


def backup_first(source: Path | None = None, directory: Path | None = None) -> Path | None:
    """Save a copy of the database before anything is written. A backup problem never stops the update."""
    try:
        from scripts.backup_database import BACKUP_DIR, create_backup
        from app.db.database import resolve_database_path

        database = source or resolve_database_path()
        if not Path(database).is_file():
            return None
        # JOBPILOT_BACKUP_DIR lets tests (or you) keep these copies somewhere else.
        target = directory or Path(os.getenv("JOBPILOT_BACKUP_DIR") or BACKUP_DIR)
        return create_backup(Path(database), target)  # a regular backup: the latest 14 are kept
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: could not back up the database first ({type(exc).__name__}: {exc})", flush=True)
        return None


def load_steps(argv: list[str]) -> list[list]:
    if len(argv) > 1:
        with open(argv[1], encoding="utf-8") as handle:
            return json.load(handle)
    from app.services.sync_runner import STEPS

    return [[name, args] for name, args in STEPS]


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv
    steps = load_steps(argv)
    saved = backup_first()
    print(f"=== Database backup: {saved.name if saved else 'skipped'} ===", flush=True)
    for name, args in steps:
        print(f"=== STEP {name} ===", flush=True)
        code = run_step(args)
        print(f"=== STEP {name} EXIT {code} ===", flush=True)
    print("=== DONE ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
