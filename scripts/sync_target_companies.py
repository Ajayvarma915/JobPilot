from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.collectors.google_careers import GoogleCareersCollector
from app.collectors.greenhouse import GreenhouseCollector
from app.collectors.lever import LeverCollector
from app.collectors.ashby import AshbyCollector
from app.collectors.smartrecruiters import SmartRecruitersCollector
from app.collectors.workday import WorkdayCollector
from app.collectors.amazon_jobs import AmazonJobsCollector
from app.collectors.oracle_hcm import OracleHCMCollector
from app.db.database import SessionLocal
from app.db.job_repository import JobRepository
from app.services.target_role_policy import is_target_software_role, is_india_or_remote_eligible

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / "data" / "target_companies.json"


@dataclass
class SyncResult:
    company: str
    provider: str
    status: str
    collected: int = 0
    eligible: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    error: str | None = None


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    companies = payload.get("companies")
    if not isinstance(companies, list) or len(companies) != 30:
        raise ValueError("target_companies.json must contain exactly 30 companies")
    ids = [item.get("id") for item in companies]
    if len(ids) != len(set(ids)):
        raise ValueError("Target company IDs must be unique")
    return payload


class _CompositeCollector:
    """Combine multiple keyword searches into one deduplicated company feed."""

    def __init__(self, collectors: list[Any]) -> None:
        self.collectors = collectors

    def collect(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for collector in self.collectors:
            for job in collector.collect():
                identity = str(job.get("external_id") or job.get("url") or "").strip()
                if not identity or identity in seen:
                    continue
                seen.add(identity)
                results.append(job)
        return results


def _make_collector(company: dict[str, Any]) -> Any:
    integration = company.get("integration") or {}
    provider = integration.get("provider")
    settings = integration.get("settings") or {}
    name = str(company["name"])
    website = company.get("website")
    careers_url = company.get("careers_url")

    if provider == "oracle_hcm":
        return OracleHCMCollector(
            base_url=str(settings["base_url"]),
            site_number=str(settings["site_number"]),
            company_name=name,
            language=str(settings.get("language") or "en"),
            country_code=str(settings.get("country_code") or "IN"),
            page_size=int(settings.get("page_size", 100)),
            max_pages=int(settings.get("max_pages", 20)),
        )
    if provider == "amazon_jobs":
        return AmazonJobsCollector(
            company_name=name,
            max_pages_per_band=int(settings.get("max_pages_per_band", 4)),
            page_size=int(settings.get("page_size", 100)),
            fetch_details=bool(settings.get("fetch_details", True)),
            max_detail_fetch=int(settings.get("max_detail_fetch", 200)),
            experience_bands=tuple(settings.get("experience_bands", ["less_than_one_year", "one_to_three_years"])),
        )
    if provider == "google_careers":
        queries = settings.get("queries")
        if not isinstance(queries, list) or not queries:
            queries = [str(settings.get("query") or "software engineer")]
        collectors = [
            GoogleCareersCollector(
                query=str(query),
                location=str(settings.get("location") or "India"),
                max_pages=int(settings.get("max_pages_per_query", settings.get("max_pages", 5))),
                fetch_details=bool(settings.get("fetch_details", True)),
            )
            for query in queries
            if str(query).strip()
        ]
        return _CompositeCollector(collectors)
    if provider == "greenhouse":
        return GreenhouseCollector(
            board_token=str(settings["board_token"]),
            company_name=name,
            website=website,
            careers_url=careers_url,
        )
    if provider == "lever":
        return LeverCollector(
            site=str(settings["site"]),
            company_name=name,
            region=str(settings.get("region") or "global"),
            website=website,
            careers_url=careers_url,
        )
    if provider == "ashby":
        return AshbyCollector(
            board_name=str(settings["board_name"]),
            company_name=name,
            website=website,
            careers_url=careers_url,
        )
    if provider == "smartrecruiters":
        return SmartRecruitersCollector(
            company_identifier=str(settings["company_identifier"]),
            company_name=name,
            website=website,
            careers_url=careers_url,
            page_size=int(settings.get("page_size", 100)),
            max_pages=int(settings.get("max_pages", 20)),
        )
    if provider == "workday":
        return WorkdayCollector(
            tenant=str(settings["tenant"]),
            site=str(settings["site"]),
            company_name=name,
            host=str(settings["host"]),
            locale=str(settings.get("locale") or "en-US"),
            website=website,
            careers_url=careers_url,
            page_size=int(settings.get("page_size", 20)),
            max_pages=int(settings.get("max_pages", 25)),
            fetch_details=bool(settings.get("fetch_details", True)),
        )
    raise ValueError(f"No configured public API connector for provider: {provider!r}")


def sync_company(
    company: dict[str, Any],
    *,
    dry_run: bool,
    maximum_required_years: float,
    allow_unverified: bool = False,
) -> SyncResult:
    integration = company.get("integration") or {}
    provider = str(integration.get("provider") or "unconfigured")
    result = SyncResult(company=str(company["name"]), provider=provider, status="pending")
    is_active = bool(integration.get("verified")) and integration.get("status") == "active"
    is_configured = bool(provider and integration.get("settings"))
    if not is_active and not (allow_unverified and is_configured):
        result.status = str(integration.get("status") or "source_not_verified")
        return result

    jobs = _make_collector(company).collect()
    result.collected = len(jobs)
    eligible_jobs = []
    for job in jobs:
        accepted, _reason = is_target_software_role(
            str(job.get("title") or ""),
            str(job.get("description") or ""),
            maximum_required_years=maximum_required_years,
        )
        if accepted:
            location_ok, location_reason = is_india_or_remote_eligible(job)
            if location_ok:
                job["jobpilot_location_screen"] = location_reason
                eligible_jobs.append(job)
            else:
                result.skipped += 1
        else:
            result.skipped += 1
    result.eligible = len(eligible_jobs)

    if dry_run:
        result.status = "dry_run" if is_active else "dry_run_unverified"
        return result

    db = SessionLocal()
    try:
        repository = JobRepository(db)
        for record in eligible_jobs:
            external_id = str(record.get("external_id") or "").strip()
            url = str(record.get("url") or "").strip()
            title = str(record.get("title") or "").strip()
            if not external_id or not url or not title:
                result.skipped += 1
                continue
            company_obj = repository.get_or_create_company(
                name=str(company["name"]),
                website=company.get("website"),
                careers_url=company.get("careers_url"),
                source_type=provider,
            )
            record["source"] = str(record.get("source") or provider)
            record["company"] = str(company["name"])
            _job, created = repository.upsert_job(company=company_obj, job_data=record)
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync verified public job feeds for JobPilot's 30 target companies.")
    parser.add_argument("--only", action="append", default=[], help="Company ID (for example google, nvidia, cred); repeatable.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and filter jobs without writing to SQLite.")
    parser.add_argument("--max-years", type=float, default=2.0, help="Maximum required experience years (default: 2).")
    parser.add_argument("--include-unverified", action="store_true", help="Try configured but not yet live-verified source mappings. Requires --dry-run.")
    args = parser.parse_args()
    if args.include_unverified and not args.dry_run:
        parser.error("--include-unverified is read-only and can only be used together with --dry-run")

    try:
        registry = load_registry()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"REGISTRY ERROR: {type(exc).__name__}: {exc}")
        return 2

    companies = registry["companies"]
    if args.only:
        requested = set(args.only)
        known = {str(item["id"]) for item in companies}
        unknown = requested - known
        if unknown:
            print("Unknown company ID(s): " + ", ".join(sorted(unknown)))
            return 2
        companies = [item for item in companies if item["id"] in requested]

    print("JobPilot — 30-company target source sync")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'DATABASE UPSERT'}")
    print(f"Candidate experience start: {registry['candidate']['experience_start_date']}")
    print(f"Maximum required experience: {args.max_years:g} years")
    print("Salary disclosure is NOT required for discovery. Compensation estimates are a separate layer.")
    print("Location: India roles + remote listings (country eligibility unverified remains flagged for review).")
    if args.include_unverified:
        print("WARNING: Trying configured-but-unverified sources in read-only DRY RUN; no database writes will occur.")
    print()

    results: list[SyncResult] = []
    for company in companies:
        integration = company.get("integration") or {}
        is_active = bool(integration.get("verified")) and integration.get("status") == "active"
        is_configured_unverified = bool(integration.get("provider") and integration.get("settings"))
        if not is_active and not (args.include_unverified and is_configured_unverified):
            results.append(SyncResult(
                company=company["name"],
                provider=str(integration.get("provider") or "not_mapped"),
                status=str(integration.get("status") or "pending_ats_discovery"),
            ))
            continue
        provider = str(integration.get("provider") or "unknown")
        print(f"[{company['name']}] {provider}: collecting...")
        try:
            row = sync_company(
                company,
                dry_run=args.dry_run,
                maximum_required_years=args.max_years,
                allow_unverified=args.include_unverified,
            )
            results.append(row)
            print(f"  {row.status}: raw={row.collected}, eligible={row.eligible}, inserted={row.inserted}, updated={row.updated}, filtered={row.skipped}")
        except Exception as exc:
            row = SyncResult(company=company["name"], provider=provider, status="failed", error=f"{type(exc).__name__}: {exc}")
            results.append(row)
            print(f"  FAILED: {row.error}")

    print("\nSummary")
    print("-" * 88)
    print(f"Companies in registry : {len(registry['companies'])}")
    print(f"Companies requested   : {len(companies)}")
    print(f"Verified API sources  : {sum(r.status in {'success','dry_run'} for r in results)}")
    print(f"Unverified dry-runs   : {sum(r.status == 'dry_run_unverified' for r in results)}")
    print(f"Awaiting source mapping: {sum(r.status not in {'success','dry_run','dry_run_unverified','failed'} for r in results)}")
    print(f"Failed API sources    : {sum(r.status == 'failed' for r in results)}")
    print(f"Raw jobs collected    : {sum(r.collected for r in results)}")
    print(f"Eligible software jobs: {sum(r.eligible for r in results)}")
    print(f"New database records  : {sum(r.inserted for r in results)}")
    print(f"Updated records       : {sum(r.updated for r in results)}")
    print("\nUnmapped company career pages are listed in data/target_companies.json. Run scripts/discover_company_ats.py from Windows, then verify candidate board IDs before enabling them.")
    return 1 if any(r.status == "failed" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
