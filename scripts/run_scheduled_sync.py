"""Unattended sync entry point for Windows Task Scheduler (or a manual run).

It syncs ONLY verified, active sources into the database (the same rules as
`python -m scripts.sync_target_companies`), then prints and saves a short summary of what
changed since the last run. It never submits applications and never sends anything.

Examples (PowerShell, from the project folder):

    # one FAST sync, then a one-day summary
    .\\venv\\Scripts\\python.exe -m scripts.run_scheduled_sync --mode fast --summary-days 1

    # weekly FULL sync (also detects jobs removed from their source)
    .\\venv\\Scripts\\python.exe -m scripts.run_scheduled_sync --mode full --summary-days 7

Register it with Windows Task Scheduler, e.g. every day at 08:00:

    schtasks /Create /SC DAILY /ST 08:00 /TN "JobPilot daily sync" ^
      /TR "D:\\Full stack Projects\\Automatic Job Apllication\\venv\\Scripts\\python.exe -m scripts.run_scheduled_sync --mode fast --summary-days 1" ^
      /RU %USERNAME%
    (add /SD and /SC WEEKLY /D MON for a weekly FULL run; the task must start in the project folder)

Use JOBPILOT_DATABASE_PATH to point at a different database.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from app.db.database import SessionLocal, resolve_database_path
from app.services.sync_summary import build_change_summary
from scripts import sync_target_companies

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = PROJECT_ROOT / "data" / "sync_reports"


def format_summary(summary: dict) -> str:
    lines = [
        f"JobPilot sync summary - last {summary['window_days']} day(s) (generated {summary['generated_at']})",
        f"Active jobs: {summary['jobs_active']} | inactive: {summary['jobs_inactive']}",
    ]
    if not summary["tracking_available"]:
        lines.append(summary.get("note") or "No change history yet.")
        return "\n".join(lines)
    counts = summary["counts"]
    lines.append(
        f"New: {counts['created']} | Updated: {counts['updated']} | "
        f"Reactivated: {counts['reactivated']} | Removed: {counts['removed']}"
    )
    for item in summary["by_company"][:15]:
        lines.append(
            f"  {item['company']}: +{item['created']} new, {item['updated']} updated, "
            f"{item['reactivated']} reactivated, {item['removed']} removed"
        )
    for event in summary["recent"][:20]:
        fields = f" ({', '.join(event['changed_fields'])})" if event["changed_fields"] else ""
        lines.append(f"  [{event['event']}] {event['company']} - {event['title']}{fields}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync verified sources, then summarise what changed.")
    parser.add_argument("--mode", choices=("full", "fast"), default="fast")
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--summary-days", type=int, default=1)
    args = parser.parse_args()

    print(f"Database: {resolve_database_path()}")
    code = sync_target_companies.main(
        ["--mode", args.mode, "--concurrency", str(args.concurrency)]
    )

    session = SessionLocal()
    try:
        text = format_summary(build_change_summary(session, days=args.summary_days))
    finally:
        session.close()
    print("\n" + text)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = REPORT_DIR / f"sync_{datetime.now():%Y%m%d_%H%M%S}.txt"
    report.write_text(text + "\n", encoding="utf-8")
    print(f"\nSummary saved to {report}")
    return code


if __name__ == "__main__":
    sys.exit(main())
