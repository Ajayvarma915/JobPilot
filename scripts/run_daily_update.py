"""The scheduled daily update: the same update as the app's "Update jobs now" button, with a kept history.

    python -m scripts.run_daily_update

If an update is already running, this one is skipped. Each run is appended to data/daily_update.log.
Exit code 0 means every step finished (or the run was skipped); 1 means something failed.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from app.services import sync_runner

# The history is cut back to its newest part once it grows past this size.
MAX_HISTORY_BYTES = 2_000_000


def _append(history: Path, text: str) -> None:
    history.parent.mkdir(parents=True, exist_ok=True)
    if history.is_file() and history.stat().st_size > MAX_HISTORY_BYTES:
        history.write_bytes(history.read_bytes()[-MAX_HISTORY_BYTES // 2:])
    with open(history, "a", encoding="utf-8") as handle:
        handle.write(text)


def main(history: Path | None = None) -> int:
    history = history or sync_runner.DATA_DIR / "daily_update.log"
    header = f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} daily update =====\n"
    try:
        result = sync_runner.run_and_wait()
    except Exception as exc:  # noqa: BLE001 - a scheduled run has no screen, so the reason must reach the log
        _append(history, header + f"Could not run the update: {type(exc).__name__}: {exc}\n")
        return 1
    if result is None:
        _append(history, header + "Skipped: an update was already running.\n")
        return 0
    try:
        output = sync_runner.LOG_FILE.read_text(encoding="utf-8", errors="replace")
    except OSError:
        output = "(the update wrote no log)\n"
    ok = result["state"] == "finished"
    _append(history, header + output + f"===== result: {'finished' if ok else 'FAILED, see the steps above'} =====\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
