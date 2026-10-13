from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.collectors.google_careers import GoogleCareersCollector
from app.collectors.greenhouse import GreenhouseCollector
from app.collectors.lever import LeverCollector
from app.db.database import SessionLocal
from app.db.job_repository import JobRepository


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "data" / "job_sources.json"

GOOGLE_CAREERS_HOME = "https://www.google.com/about/careers/"


@dataclass
class SourceResult:
    name: str
    collected: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    status: str = "pending"
    error: str | None = None


@dataclass
class ConfiguredSource:
    name: str
    company_fallback: str
    website: str | None
    careers_url: str | None
    build_collector: Callable[[], Any]


def load_config(path: Path) -> dict[str, Any]:
    """Load and validate the source configuration JSON."""
    if not path.is_file():
        raise FileNotFoundError(
            f"Job-source configuration not found: {path}\n"
            "Create it using data/job_sources.json."
        )

    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)

    if not isinstance(config, dict):
        raise ValueError(
            "The source configuration must be a JSON object."
        )

    return config


def _build_google_factory(
    query: str,
    location: str,
    max_pages: int,
    fetch_details: bool,
) -> Callable[[], GoogleCareersCollector]:
    """Capture this Google configuration in a separate factory function."""

    def build() -> GoogleCareersCollector:
        return GoogleCareersCollector(
            query=query,
            location=location,
            fetch_details=fetch_details,
            max_pages=max_pages,
        )

    return build


def _build_greenhouse_factory(
    entry: dict[str, Any],
) -> Callable[[], GreenhouseCollector]:
    """Create a factory for one Greenhouse board."""

    def build() -> GreenhouseCollector:
        return GreenhouseCollector(
            board_token=str(entry["board_token"]),
            company_name=str(entry["company_name"]),
            website=entry.get("website"),
            careers_url=entry.get("careers_url"),
        )

    return build


def _build_lever_factory(
    entry: dict[str, Any],
) -> Callable[[], LeverCollector]:
    """Create a factory for one Lever site."""

    def build() -> LeverCollector:
        return LeverCollector(
            site=str(entry["site"]),
            company_name=str(entry["company_name"]),
            region=str(entry.get("region") or "global").casefold(),
            website=entry.get("website"),
            careers_url=entry.get("careers_url"),
        )

    return build


def configured_sources(
    config: dict[str, Any],
) -> list[ConfiguredSource]:
    """Convert enabled JSON entries into configured source factories."""
    result: list[ConfiguredSource] = []

    # Google Careers
    google = config.get("google", {})

    if not isinstance(google, dict):
        raise ValueError("'google' must be a JSON object.")

    if google.get("enabled", False):
        query = str(google.get("query") or "Software Engineer")
        location = str(google.get("location") or "Hyderabad")
        max_pages = int(google.get("max_pages", 2))
        fetch_details = bool(google.get("fetch_details", True))
        company_name = str(google.get("company_name") or "Google")

        if max_pages < 1:
            raise ValueError("Google max_pages must be at least 1.")

        result.append(
            ConfiguredSource(
                name="google",
                company_fallback=company_name,
                website=google.get("website"),
                careers_url=google.get(
                    "careers_url",
                    GOOGLE_CAREERS_HOME,
                ),
                build_collector=_build_google_factory(
                    query=query,
                    location=location,
                    max_pages=max_pages,
                    fetch_details=fetch_details,
                ),
            )
        )

    # Greenhouse boards
    greenhouse = config.get("greenhouse", [])

    if not isinstance(greenhouse, list):
        raise ValueError("'greenhouse' must be a JSON array.")

    for entry in greenhouse:
        if not isinstance(entry, dict):
            raise ValueError(
                "Each Greenhouse entry must be an object."
            )

        if not entry.get("enabled", False):
            continue

        token = str(entry.get("board_token") or "").strip()
        company_name = str(entry.get("company_name") or "").strip()

        if not token or not company_name:
            raise ValueError(
                "Enabled Greenhouse entries need board_token "
                "and company_name."
            )

        result.append(
            ConfiguredSource(
                name=f"greenhouse:{token.casefold()}",
                company_fallback=company_name,
                website=entry.get("website"),
                careers_url=entry.get("careers_url"),
                build_collector=_build_greenhouse_factory(entry),
            )
        )

    # Lever sites
    lever = config.get("lever", [])

    if not isinstance(lever, list):
        raise ValueError("'lever' must be a JSON array.")

    for entry in lever:
        if not isinstance(entry, dict):
            raise ValueError(
                "Each Lever entry must be an object."
            )

        if not entry.get("enabled", False):
            continue

        site = str(entry.get("site") or "").strip()
        company_name = str(entry.get("company_name") or "").strip()
        region = str(entry.get("region") or "global").strip().casefold()

        if not site or not company_name:
            raise ValueError(
                "Enabled Lever entries need site and company_name."
            )

        if region not in LeverCollector.API_ROOTS:
            raise ValueError(
                f"Unsupported Lever region '{region}' for site '{site}'."
            )

        result.append(
            ConfiguredSource(
                name=f"lever:{region}:{site.casefold()}",
                company_fallback=company_name,
                website=entry.get("website"),
                careers_url=entry.get("careers_url"),
                build_collector=_build_lever_factory(entry),
            )
        )

    return result


def import_source(
    source: ConfiguredSource,
    jobs: list[dict[str, Any]],
    *,
    dry_run: bool,
) -> SourceResult:
    """Upsert collected jobs unless running in dry-run mode."""
    result = SourceResult(
        name=source.name,
        collected=len(jobs),
    )

    if dry_run:
        result.status = "dry-run"
        return result

    db = SessionLocal()

    try:
        repository = JobRepository(db)

        for record in jobs:
            title = str(record.get("title") or "").strip()
            job_url = str(record.get("url") or "").strip()

            source_name = str(
                record.get("source") or source.name
            ).strip()

            company_name = str(
                record.get("company") or source.company_fallback
            ).strip()

            if not title or not job_url or not source_name or not company_name:
                result.skipped += 1
                continue

            clean_record = dict(record)
            clean_record["title"] = title
            clean_record["url"] = job_url
            clean_record["company"] = company_name
            clean_record["source"] = source_name

            company = repository.get_or_create_company(
                name=company_name,
                website=source.website,
                careers_url=source.careers_url,
                source_type=source_name,
            )

            _, created = repository.upsert_job(
                company=company,
                job_data=clean_record,
            )

            if created:
                result.inserted += 1
            else:
                result.updated += 1

        db.commit()
        result.status = "success"
        return result

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collect jobs from configured Google Careers, Greenhouse, "
            "and Lever sources and upsert them into JobPilot's database."
        )
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"Source configuration JSON (default: {DEFAULT_CONFIG})",
    )

    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help=(
            "Only run a named source. Repeat for multiple sources, e.g. "
            "--only google --only greenhouse:coinbase."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Collect and report source counts without writing to the database."
        ),
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    print("=" * 72)
    print("JobPilot Multi-Source Job Synchronization")
    print("=" * 72)
    print(f"Config: {args.config}")
    print(
        "Database: "
        + ("not modified" if args.dry_run else "JobPilot SQLite")
    )
    print(f"Mode: {'dry run' if args.dry_run else 'database sync'}")
    print()

    try:
        config = load_config(args.config)
        sources = configured_sources(config)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"CONFIGURATION ERROR: {exc}", file=sys.stderr)
        return 2

    if args.only:
        requested = set(args.only)
        available = {source.name for source in sources}
        not_found = requested - available

        if not_found:
            print(
                "Unknown or disabled source(s): "
                + ", ".join(sorted(not_found)),
                file=sys.stderr,
            )
            return 2

        sources = [
            source for source in sources
            if source.name in requested
        ]

    if not sources:
        print(
            "No sources are enabled in the configuration.",
            file=sys.stderr,
        )
        return 2

    results: list[SourceResult] = []

    for source in sources:
        print(f"[{source.name}] Collecting...")

        try:
            collector = source.build_collector()
            jobs = collector.collect()

            result = import_source(
                source,
                jobs,
                dry_run=args.dry_run,
            )
            results.append(result)

            print(
                f"[{source.name}] {result.status}: "
                f"collected={result.collected}, "
                f"inserted={result.inserted}, "
                f"updated={result.updated}, "
                f"skipped={result.skipped}"
            )

        except Exception as exc:
            results.append(
                SourceResult(
                    name=source.name,
                    status="failed",
                    error=f"{type(exc).__name__}: {exc}",
                )
            )

            print(
                f"[{source.name}] FAILED: "
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr,
            )

    print()
    print("=" * 72)
    print("Synchronization Summary")
    print("=" * 72)

    for result in results:
        print(
            f"{result.name:30} {result.status:10} "
            f"collected={result.collected:4} "
            f"inserted={result.inserted:4} "
            f"updated={result.updated:4} "
            f"skipped={result.skipped:4}"
        )

        if result.error:
            print(f"    Error: {result.error}")

    total_collected = sum(item.collected for item in results)
    total_inserted = sum(item.inserted for item in results)
    total_updated = sum(item.updated for item in results)
    failed = sum(item.status == "failed" for item in results)

    print(f"Total collected: {total_collected}")
    print(f"Total inserted : {total_inserted}")
    print(f"Total updated  : {total_updated}")
    print(f"Failed sources : {failed}")

    if failed:
        print(
            "Completed with source errors; check the failed entries above."
        )
        return 1

    print("SUCCESS: all configured source runs completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())