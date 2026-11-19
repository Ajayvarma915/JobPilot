"""Sync remote jobs from public remote job boards (Remotive, Remote OK, Himalayas, We Work Remotely).

    python -m scripts.sync_remote_boards                 # all four boards, write to the database
    python -m scripts.sync_remote_boards --dry-run       # fetch and report only
    python -m scripts.sync_remote_boards --only remotive # one board

The same deterministic eligibility rules as the company sync apply (software role, early career,
open to India or worldwide). Jobs that pass cleanly are stored for the Remote jobs tab; ambiguous ones
are stored held for your review; everything else is dropped. A job that leaves a board is marked
closed, but only when the board answered with a believable number of jobs.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from typing import Any

from app.collectors.remote_boards import COLLECTORS
from app.db.database import SessionLocal
from app.db.job_repository import JobRepository
from app.services.target_role_policy import ELIGIBLE, ELIGIBLE_NEEDS_REVIEW, evaluate_eligibility


@dataclass
class BoardResult:
    board: str
    status: str = "pending"
    collected: int = 0
    clean: int = 0
    review: int = 0
    skipped: int = 0
    inserted: int = 0
    updated: int = 0
    removed: int = 0
    note: str | None = None
    error: str | None = None
    skip_reasons: dict[str, int] = field(default_factory=dict)


# A feed may say "Anywhere" while the title names the real restriction, e.g. "(Remote @ Colombia)",
# "(U.S. Based)" or "Remote Eligible in Bulgaria". Those are not open to India.
_TITLE_RESTRICTION = re.compile(
    r"remote\s*@|eligible in|(?:based|located|residing|resident) in|"
    r"(?<![a-z])(?:u\.?s\.?a?|uk|canada|emea|latam|europe)(?![a-z])[ -]*(?:based|only|residents?)",
    re.IGNORECASE,
)
_OPEN_TO_INDIA = ("india_location", "remote_india_or_global_eligible")


def sync_board(board: str, jobs: list[dict[str, Any]], *, source: str, dry_run: bool, max_years: float) -> BoardResult:
    result = BoardResult(board=board, collected=len(jobs))
    keep: list[tuple[dict[str, Any], list[str]]] = []
    for job in jobs:
        decision = evaluate_eligibility(job, source_verified=True, maximum_required_years=max_years)
        drop = None
        if decision.passes_filters and _TITLE_RESTRICTION.search(str(job.get("title") or "")):
            drop = "title_names_a_region_outside_india"
        elif decision.passes_filters and decision.location_reason not in _OPEN_TO_INDIA:
            drop = "region_not_open_to_india"  # a named place or an unrecognised region on a remote board
        if drop:
            result.skipped += 1
            result.skip_reasons[drop] = result.skip_reasons.get(drop, 0) + 1
            continue
        if decision.status == ELIGIBLE:
            result.clean += 1
            keep.append((job, []))
        elif decision.status == ELIGIBLE_NEEDS_REVIEW:
            result.review += 1
            keep.append((job, list(decision.flags) or ["needs_review"]))
        else:
            result.skipped += 1
            reason = decision.reasons[0] if decision.reasons else "excluded"
            result.skip_reasons[reason] = result.skip_reasons.get(reason, 0) + 1
    if dry_run:
        result.status = "dry_run"
        return result

    db = SessionLocal()
    try:
        repository = JobRepository(db)
        for job, flags in keep:
            company = repository.get_or_create_company(name=str(job["company"]), source_type="remote_board")
            outcome = repository.upsert_job_detailed(company=company, job_data=job)
            if flags:
                repository.set_review(outcome.job, flags)
            else:
                repository.clear_pending_review(outcome.job)
            if outcome.status == "created":
                result.inserted += 1
            elif outcome.status in ("updated", "reactivated"):
                result.updated += 1
        # Closure detection mixes many employers in one feed, so it is judged on the whole board:
        # only jobs this run actually considered count as "still listed", and a small answer closes nothing.
        stored = repository.active_source_count(source)
        listed_ids = {str(job["external_id"]) for job in jobs}
        if stored and len(jobs) < stored * 0.5:
            result.note = f"closure check skipped: the board listed {len(jobs)} jobs against {stored} stored"
        else:
            # Jobs this board listed but we dropped (no longer eligible) are not "closed", just not wanted.
            result.removed = len(repository.mark_source_missing_inactive(source, listed_ids))
        db.commit()
        result.status = "success"
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync remote jobs from public remote job boards.")
    parser.add_argument("--only", action="append", default=[], choices=sorted(COLLECTORS), help="Board to sync; repeatable.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and report without writing to the database.")
    parser.add_argument("--max-years", type=float, default=2.0, help="Maximum required experience (default 2).")
    args = parser.parse_args(argv)

    boards = args.only or list(COLLECTORS)
    results: list[BoardResult] = []
    for board in boards:
        collector = COLLECTORS[board]()
        print(f"[{board}] collecting...")
        try:
            jobs = collector.collect()
            result = sync_board(board, jobs, source=collector.source, dry_run=args.dry_run, max_years=args.max_years)
        except Exception as exc:  # noqa: BLE001 - one board failing must not stop the others
            result = BoardResult(board=board, status="failed", error=f"{type(exc).__name__}: {str(exc)[:160]}")
        results.append(result)
        if result.error:
            print(f"  FAILED: {result.error}")
        else:
            top = ", ".join(f"{k}={v}" for k, v in sorted(result.skip_reasons.items(), key=lambda kv: -kv[1])[:4])
            print(f"  {result.status}: raw={result.collected}, clean={result.clean}, held_for_review={result.review}, "
                  f"inserted={result.inserted}, updated={result.updated}, closed={result.removed}, dropped={result.skipped}"
                  + (f" ({top})" if top else "") + (f"  NOTE: {result.note}" if result.note else ""))
    failed = [r for r in results if r.error]
    print(f"\nBoards: {len(results) - len(failed)} ok, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
