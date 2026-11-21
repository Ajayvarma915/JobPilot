"""Runs the job update: a database backup, then the update steps one after another, with progress markers.

Started by the app's "Update jobs now" button (app/services/sync_runner.py) as its own process, so a
restart of the web server does not stop it, and by the daily scheduled task (scripts/daily_update.ps1).

    python -m scripts.run_job_update                # the default steps (company pages, then remote boards)
    python -m scripts.run_job_update steps.json     # steps from a file: [[name, [python args...]], ...]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


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
        code = subprocess.call([sys.executable, "-u", *args])
        print(f"=== STEP {name} EXIT {code} ===", flush=True)
    print("=== DONE ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
