from __future__ import annotations

import argparse
import csv
import json
import re
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
from app.services.target_role_policy import (
    extract_minimum_experience_years,
    is_target_software_role,
    is_india_or_remote_eligible,
)

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
    review_required: int = 0
    auto_sync_eligible: int = 0
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
    """Combine keyword searches, deduplicate cards, then enrich each job once."""

    def __init__(
        self,
        collectors: list[Any],
        *,
        fetch_details: bool = True,
    ) -> None:
        self.collectors = collectors
        self.fetch_details = fetch_details

    def collect(self) -> list[dict[str, Any]]:
        # Google search terms overlap heavily. Collect lightweight result cards
        # first, then fetch full descriptions only once per unique job ID.
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for collector in self.collectors:
            for job in collector.collect():
                identity = str(job.get("external_id") or job.get("url") or "").strip()
                if not identity or identity in seen:
                    continue
                seen.add(identity)
                results.append(job)

        print(
            f"Google search batches produced {len(results)} unique jobs "
            "after cross-query deduplication."
        )

        if self.fetch_details and results:
            detail_collector = next(
                (collector for collector in self.collectors
                 if hasattr(collector, "enrich_jobs")),
                None,
            )
            if detail_collector is not None:
                results = detail_collector.enrich_jobs(results)
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
        # Detail fetching is deliberately deferred until all keyword results
        # have been deduplicated by _CompositeCollector.
        collectors = [
            GoogleCareersCollector(
                query=str(query),
                location=str(settings.get("location") or "India"),
                max_pages=int(settings.get("max_pages_per_query", settings.get("max_pages", 5))),
                fetch_details=False,
                detail_workers=int(settings.get("detail_workers", 3)),
            )
            for query in queries
            if str(query).strip()
        ]
        return _CompositeCollector(
            collectors,
            fetch_details=bool(settings.get("fetch_details", True)),
        )
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


_BROAD_TITLE_REVIEW_RE = re.compile(
    r"\b(?:application engineer|cloud engineer|cloud ai engineer|data and ai engineer|"
    r"salesforce application engineer|solutions engineer)\b",
    re.IGNORECASE,
)

AUDIT_FIELDS = [
    "company_id", "company", "provider", "mapping_status", "mapping_verified",
    "external_id", "title", "url", "locations", "workplace_type", "employment_type",
    "posted_at", "experience_level", "minimum_required_years", "experience_screen",
    "role_eligible", "role_reason", "location_eligible", "location_reason",
    "final_eligible", "auto_sync_eligible", "audit_status", "review_flags",
    "possible_duplicate_group_size", "description_present", "description_length",
    "description_preview", "minimum_qualification_excerpt",
]


def _location_values(job: dict[str, Any]) -> list[str]:
    value = job.get("location") or []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _minimum_qualification_excerpt(description: str, limit: int = 1200) -> str:
    """Return a bounded excerpt from the JD's minimum/basic qualifications."""
    start_re = re.compile(
        r"(?:minimum qualifications|required qualifications|basic qualifications|minimum requirements|"
        r"required experience|requirements)",
        re.IGNORECASE,
    )
    end_re = re.compile(
        r"(?:preferred qualifications|nice to have|preferred skills|bonus points|"
        r"about the team|responsibilities|what you'll do|what you will do)",
        re.IGNORECASE,
    )
    start = start_re.search(description or "")
    if not start:
        return ""
    tail = (description or "")[start.end():]
    end = end_re.search(tail)
    section = tail[:end.start()] if end else tail
    return re.sub(r"\s+", " ", section).strip()[:limit]


def _normalize_duplicate_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold())).strip()


def _mark_possible_duplicates(rows: list[dict[str, Any]]) -> None:
    """Flag, but never delete, candidate postings with the same title/location/JD prefix."""
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if not row.get("final_eligible"):
            continue
        description_key = _normalize_duplicate_text(str(row.get("description_preview") or ""))
        if not description_key:
            continue
        key = (
            str(row.get("company") or "").casefold(),
            _normalize_duplicate_text(str(row.get("title") or "")),
            _normalize_duplicate_text(str(row.get("locations") or "")),
            description_key,
        )
        groups.setdefault(key, []).append(row)

    for group in groups.values():
        if len(group) < 2:
            continue
        for row in group:
            existing = [flag for flag in str(row.get("review_flags") or "").split(";") if flag]
            if "possible_duplicate_posting_review" not in existing:
                existing.append("possible_duplicate_posting_review")
            row["review_flags"] = ";".join(existing)
            row["possible_duplicate_group_size"] = len(group)
            row["audit_status"] = "eligible_needs_review"
            row["auto_sync_eligible"] = False


def _make_audit_row(
    company: dict[str, Any], job: dict[str, Any], maximum_required_years: float
) -> dict[str, Any]:
    integration = company.get("integration") or {}
    provider = str(integration.get("provider") or "unconfigured")
    title = str(job.get("title") or "").strip()
    description = str(job.get("description") or "")
    minimum_years = extract_minimum_experience_years(description)
    role_ok, role_reason = is_target_software_role(
        title, description, maximum_required_years=maximum_required_years
    )
    location_ok, location_reason = is_india_or_remote_eligible(job)
    flags: list[str] = []
    if not description.strip():
        flags.append("description_missing")
    if minimum_years is None:
        flags.append("minimum_experience_not_found_review")
    if location_reason == "remote_country_eligibility_unverified":
        flags.append("remote_country_eligibility_unverified")
    if _BROAD_TITLE_REVIEW_RE.search(title):
        flags.append("broad_title_manual_review")
    mapping_verified = bool(integration.get("verified")) and integration.get("status") == "active"
    final_ok = role_ok and location_ok
    if final_ok and not mapping_verified:
        flags.append("source_mapping_unverified_review")
    status = "filtered"
    if final_ok:
        status = "eligible_needs_review" if flags else "eligible"
    preview = re.sub(r"\s+", " ", description).strip()[:280]
    return {
        "company_id": str(company.get("id") or ""),
        "company": str(company.get("name") or ""),
        "provider": provider,
        "mapping_status": str(integration.get("status") or ""),
        "mapping_verified": bool(integration.get("verified")),
        "external_id": str(job.get("external_id") or ""),
        "title": title,
        "url": str(job.get("url") or ""),
        "locations": " | ".join(_location_values(job)),
        "workplace_type": str(job.get("workplace_type") or ""),
        "employment_type": str(job.get("employment_type") or ""),
        "posted_at": str(job.get("posted_at") or job.get("date_posted") or ""),
        "experience_level": str(job.get("experience_level") or ""),
        "minimum_required_years": minimum_years if minimum_years is not None else "",
        "experience_screen": (
            "not_found_review" if minimum_years is None
            else "within_limit" if minimum_years <= maximum_required_years
            else "above_limit"
        ),
        "role_eligible": role_ok,
        "role_reason": role_reason,
        "location_eligible": location_ok,
        "location_reason": location_reason,
        "final_eligible": final_ok,
        "auto_sync_eligible": bool(final_ok and status == "eligible" and mapping_verified),
        "audit_status": status,
        "review_flags": ";".join(flags),
        "possible_duplicate_group_size": 1,
        "description_present": bool(description.strip()),
        "description_length": len(description),
        "description_preview": preview,
        "minimum_qualification_excerpt": _minimum_qualification_excerpt(description),
    }


def write_audit_report(rows: list[dict[str, Any]], destination: Path) -> Path:
    """Write a compact per-job CSV audit without changing the application database."""
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=AUDIT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return destination


def sync_company(
    company: dict[str, Any],
    *,
    dry_run: bool,
    maximum_required_years: float,
    allow_unverified: bool = False,
    audit_rows: list[dict[str, Any]] | None = None,
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

    # Build the audit rows as a batch so probable duplicate postings can be
    # flagged before any records are considered for database upsert.
    company_audits = [
        _make_audit_row(company, job, maximum_required_years)
        for job in jobs
    ]
    _mark_possible_duplicates(company_audits)
    if audit_rows is not None:
        audit_rows.extend(company_audits)

    # Jobs that need human review remain in the CSV, but are never written to
    # SQLite by the default live-sync path.
    eligible_jobs = []
    for job, audit in zip(jobs, company_audits):
        if audit["final_eligible"]:
            result.eligible += 1
            if audit["auto_sync_eligible"]:
                result.auto_sync_eligible += 1
                job["jobpilot_location_screen"] = audit["location_reason"]
                eligible_jobs.append(job)
            else:
                result.review_required += 1
        else:
            result.skipped += 1

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
    parser.add_argument("--audit-report", type=Path, help="Write a per-job CSV eligibility audit; requires --dry-run.")
    args = parser.parse_args()
    if args.include_unverified and not args.dry_run:
        parser.error("--include-unverified is read-only and can only be used together with --dry-run")
    if args.audit_report and not args.dry_run:
        parser.error("--audit-report is read-only and can only be used together with --dry-run")

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
    audit_rows: list[dict[str, Any]] = []
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
                audit_rows=audit_rows if args.audit_report else None,
            )
            results.append(row)
            print(f"  {row.status}: raw={row.collected}, candidates={row.eligible}, auto_sync_eligible={row.auto_sync_eligible}, review_required={row.review_required}, inserted={row.inserted}, updated={row.updated}, filtered={row.skipped}")
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
    print(f"Role/location candidates: {sum(r.eligible for r in results)}")
    print(f"Auto-sync eligible jobs : {sum(r.auto_sync_eligible for r in results)}")
    print(f"Eligible needing review : {sum(r.review_required for r in results)}")
    print(f"New database records    : {sum(r.inserted for r in results)}")
    print(f"Updated records       : {sum(r.updated for r in results)}")
    if args.audit_report:
        try:
            report_path = write_audit_report(audit_rows, args.audit_report)
            print(f"Per-job audit report  : {report_path}")
            print(f"Audit rows written    : {len(audit_rows)}")
        except OSError as exc:
            print(f"AUDIT REPORT ERROR: {type(exc).__name__}: {exc}")
            return 2
    print("\nUnmapped company career pages are listed in data/target_companies.json. Run scripts/discover_company_ats.py from Windows, then verify candidate board IDs before enabling them.")
    return 1 if any(r.status == "failed" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
