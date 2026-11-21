"""Source states and health tracking for the company source registry.

The registry file says what a source is *configured* to be. The `source_health`
table says what actually happened on each fetch. Combining them gives an
explicit, auditable state per company. Nothing here promotes a source:
`verified` / `active` can only come from the registry, after a human reviewed
the evidence.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.db.models import SourceHealth

DISCOVERED = "discovered"
CONFIGURED = "configured"
AWAITING_VALIDATION = "awaiting_validation"
VERIFIED = "verified"
ACTIVE = "active"
TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
FAILED = "failed"
DEPRECATED = "deprecated"

STATES = (
    DISCOVERED, CONFIGURED, AWAITING_VALIDATION, VERIFIED, ACTIVE,
    TEMPORARILY_UNAVAILABLE, FAILED, DEPRECATED,
)

# Consecutive failed fetches after which a trusted source is shown as failed
# rather than temporarily unavailable.
FAILED_AFTER_CONSECUTIVE_FAILURES = 3

REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "target_companies.json"


def registry_state(company: dict[str, Any]) -> tuple[str, str]:
    """Map a registry entry to (state, detail). Pure and deterministic."""
    integration = company.get("integration") or {}
    status = str(integration.get("status") or "").strip().lower()
    provider = integration.get("provider")
    has_connector = bool(provider and integration.get("settings"))
    verified = bool(integration.get("verified"))

    if status in (DEPRECATED, FAILED, TEMPORARILY_UNAVAILABLE):
        return status, status
    if status == "active":
        if verified and has_connector:
            return ACTIVE, ""
        return AWAITING_VALIDATION, "marked active but verified flag or connector settings missing"
    if verified and has_connector:
        return VERIFIED, status
    if has_connector:
        if status == "configured":
            return CONFIGURED, status
        return AWAITING_VALIDATION, status or "needs_live_validation"
    # No working connector: only the company (and maybe its careers page) is known.
    return DISCOVERED, status or "no_connector"


def is_auto_sync_state(state: str) -> bool:
    """Only active sources may enter the automatic database sync."""
    return state == ACTIVE


def effective_state(configured_state: str, consecutive_failures: int = 0) -> str:
    """Downgrade a trusted source after fetch failures; never upgrade anything."""
    if configured_state in (ACTIVE, VERIFIED) and consecutive_failures > 0:
        if consecutive_failures >= FAILED_AFTER_CONSECUTIVE_FAILURES:
            return FAILED
        return TEMPORARILY_UNAVAILABLE
    return configured_state


def load_registry_companies(path: Path = REGISTRY_PATH) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    companies = payload.get("companies")
    if not isinstance(companies, list):
        raise ValueError("Registry must contain a 'companies' list")
    return companies


def ensure_source_health_table(session: Session) -> None:
    """Create the table if missing, and add columns newer than the stored table (idempotent, additive)."""
    bind = session.get_bind()
    SourceHealth.__table__.create(bind=bind, checkfirst=True)
    existing = {column["name"] for column in inspect(bind).get_columns("source_health")}
    if "exclusion_reasons" not in existing:
        with bind.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE source_health ADD COLUMN exclusion_reasons TEXT")


_REASON_LABELS = {
    "senior_or_lead_title": "senior, staff or lead titles",
    "non_software_title": "not software roles",
    "outside_target_software_role_families": "other kinds of engineering role",
    "internship_or_trainee": "internships or trainee roles",
    "phd_required_or_phd_targeted_title": "roles that need a PhD",
    "phd_required_in_minimum_qualifications": "roles that need a PhD",
    "outside_india": "outside India",
    "location_not_verified_as_india": "locations not in India",
    "missing_location": "no location given",
    "missing_title": "no title",
}


def describe_exclusions(reasons: dict[str, int] | None, limit: int = 4) -> list[dict[str, Any]]:
    """Group raw reason codes into short labels, biggest first. Pure."""
    grouped: dict[str, int] = {}
    for reason, count in (reasons or {}).items():
        label = ("ask for more experience than your limit" if reason.startswith("requires_")
                 else _REASON_LABELS.get(reason, reason.replace("_", " ")))
        grouped[label] = grouped.get(label, 0) + int(count)
    ordered = sorted(grouped.items(), key=lambda item: (-item[1], item[0]))
    return [{"label": label, "count": count} for label, count in ordered[:limit]]


def record_fetch(
    session: Session,
    *,
    company_id: str,
    company_name: str,
    provider: str | None,
    success: bool,
    counts: dict[str, int | None] | None = None,
    pagination_status: str | None = None,
    error: str | None = None,
    exclusion_reasons: dict[str, int] | None = None,
    now: datetime | None = None,
) -> SourceHealth:
    """Upsert one fetch outcome. The caller commits."""
    ensure_source_health_table(session)
    moment = now or datetime.utcnow()
    row = session.get(SourceHealth, company_id)
    if row is None:
        row = SourceHealth(company_id=company_id, company_name=company_name)
        session.add(row)
    row.company_name = company_name
    row.provider = provider
    row.last_attempt_at = moment
    row.updated_at = moment

    if success:
        counts = counts or {}
        row.last_success_at = moment
        row.consecutive_failures = 0
        row.last_error = None
        row.raw_jobs = counts.get("raw_jobs")
        row.unique_jobs = counts.get("unique_jobs")
        row.eligible_jobs = counts.get("eligible_jobs")
        row.review_jobs = counts.get("review_jobs")
        row.jobs_with_description = counts.get("jobs_with_description")
        if exclusion_reasons is not None:
            row.exclusion_reasons = json.dumps(exclusion_reasons, sort_keys=True)
        row.detail_attempted = counts.get("detail_attempted")
        row.detail_succeeded = counts.get("detail_succeeded")
        if counts.get("detail_succeeded"):
            row.last_enrichment_success_at = moment
        if pagination_status:
            row.pagination_status = pagination_status
    else:
        row.last_failure_at = moment
        row.consecutive_failures = (row.consecutive_failures or 0) + 1
        # Keep the last good counts; only the error and failure bookkeeping change.
        row.last_error = (error or "unknown error")[:1000]
    return row


def _loads(text: str | None) -> dict[str, int] | None:
    try:
        value = json.loads(text) if text else None
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def build_health_report(
    companies: list[dict[str, Any]],
    rows: dict[str, SourceHealth] | None = None,
) -> dict[str, Any]:
    """Merge registry entries with recorded fetch history. Read-only."""
    rows = rows or {}
    items: list[dict[str, Any]] = []
    for company in companies:
        company_id = str(company.get("id") or "")
        configured, detail = registry_state(company)
        row = rows.get(company_id)
        failures = (row.consecutive_failures if row else 0) or 0
        state = effective_state(configured, failures)
        integration = company.get("integration") or {}
        items.append({
            "id": company_id,
            "name": company.get("name"),
            "priority": company.get("priority"),
            "provider": integration.get("provider"),
            "careers_url": company.get("careers_url"),
            "configured_state": configured,
            "state": state,
            "state_detail": detail,
            "auto_sync_allowed": is_auto_sync_state(state),
            "never_fetched": row is None or row.last_attempt_at is None,
            "last_attempt_at": _iso(row.last_attempt_at) if row else None,
            "last_success_at": _iso(row.last_success_at) if row else None,
            "last_failure_at": _iso(row.last_failure_at) if row else None,
            "last_error": row.last_error if row else None,
            "consecutive_failures": failures,
            "exclusion_reasons": _loads(row.exclusion_reasons) if row else None,
            "why_excluded": describe_exclusions(_loads(row.exclusion_reasons)) if row else [],
            "raw_jobs": row.raw_jobs if row else None,
            "unique_jobs": row.unique_jobs if row else None,
            "eligible_jobs": row.eligible_jobs if row else None,
            "review_jobs": row.review_jobs if row else None,
            "jobs_with_description": row.jobs_with_description if row else None,
            "detail_attempted": row.detail_attempted if row else None,
            "detail_succeeded": row.detail_succeeded if row else None,
            "last_enrichment_success_at": _iso(row.last_enrichment_success_at) if row else None,
            "pagination_status": row.pagination_status if row else "not_reported",
        })

    by_state = {state: 0 for state in STATES}
    for item in items:
        by_state[item["state"]] = by_state.get(item["state"], 0) + 1
    return {
        "items": items,
        "summary": {
            "total": len(items),
            "by_state": by_state,
            "auto_sync_allowed": sum(1 for item in items if item["auto_sync_allowed"]),
            "never_fetched": sum(1 for item in items if item["never_fetched"]),
        },
    }


def load_health_rows(session: Session) -> dict[str, SourceHealth]:
    """Return recorded rows keyed by company id; empty if the table does not exist yet."""
    if not inspect(session.get_bind()).has_table(SourceHealth.__tablename__):
        return {}
    return {row.company_id: row for row in session.query(SourceHealth).all()}
