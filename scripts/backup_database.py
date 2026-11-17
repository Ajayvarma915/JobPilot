"""Back up and restore the JobPilot SQLite database.

    python -m scripts.backup_database                      # new backup in backups/, keep the latest 14
    python -m scripts.backup_database --keep 30
    python -m scripts.backup_database --list
    python -m scripts.backup_database --restore backups\\jobpilot_20261117_080000.db --yes

Backups use SQLite's online backup API, so they are safe while the app is running, and each one
is verified with an integrity check before it is kept. A restore first saves the current database
as a "pre_restore" backup, and refuses a backup that fails its integrity check. Use
JOBPILOT_DATABASE_PATH to point at a different database.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from app.db.database import PROJECT_ROOT, resolve_database_path

BACKUP_DIR = PROJECT_ROOT / "backups"
PATTERN = "jobpilot_*.db"


class BackupError(RuntimeError):
    pass


def integrity_ok(path: Path) -> bool:
    try:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            return connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            connection.close()
    except sqlite3.DatabaseError:
        return False


def _copy(source: Path, destination: Path) -> None:
    src = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(str(destination))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def create_backup(source: Path, directory: Path = BACKUP_DIR, *, keep: int = 14, label: str = "jobpilot") -> Path:
    if not source.is_file():
        raise BackupError(f"Database not found: {source}")
    if keep < 1:
        raise BackupError("--keep must be at least 1.")
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{label}_{datetime.now():%Y%m%d_%H%M%S_%f}.db"
    _copy(source, destination)
    if not integrity_ok(destination):
        destination.unlink(missing_ok=True)
        raise BackupError("The new backup failed its integrity check and was discarded.")
    # Only regular backups count toward retention; safety copies made before a restore are kept.
    regular = sorted(p for p in directory.glob("jobpilot_*.db"))
    for old in regular[:-keep]:
        old.unlink(missing_ok=True)
    return destination


def restore_backup(backup: Path, target: Path, directory: Path = BACKUP_DIR) -> Path:
    """Replace ``target`` with ``backup``; returns the safety copy of what was there before."""
    if not backup.is_file():
        raise BackupError(f"Backup not found: {backup}")
    if not integrity_ok(backup):
        raise BackupError("That backup fails its integrity check, so it was not restored.")
    directory.mkdir(parents=True, exist_ok=True)
    safety = directory / f"pre_restore_{datetime.now():%Y%m%d_%H%M%S_%f}.db"
    if target.is_file():
        _copy(target, safety)
    src = sqlite3.connect(f"file:{backup.as_posix()}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(str(target))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    if not integrity_ok(target):
        raise BackupError(f"The restored database failed its integrity check. Your previous data is in {safety}.")
    return safety


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up or restore the JobPilot database.")
    parser.add_argument("--keep", type=int, default=14, help="How many regular backups to keep (default 14).")
    parser.add_argument("--list", action="store_true", help="List existing backups.")
    parser.add_argument("--restore", type=Path, help="Restore this backup file over the current database.")
    parser.add_argument("--yes", action="store_true", help="Confirm a restore.")
    args = parser.parse_args()
    target = resolve_database_path()
    try:
        if args.list:
            for path in sorted(BACKUP_DIR.glob("*.db")):
                print(f"{path.name}  {path.stat().st_size:>12,} bytes")
            return 0
        if args.restore:
            if not args.yes:
                print(f"This will REPLACE {target} with {args.restore}. Re-run with --yes to confirm "
                      "(your current database is saved first).")
                return 2
            safety = restore_backup(args.restore, target)
            print(f"Restored. Previous database saved as {safety}")
            return 0
        destination = create_backup(target, keep=args.keep)
        print(f"Backup written and verified: {destination}")
        return 0
    except BackupError as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
