"""Daily / weekly summary of what changed in the stored jobs.

Computed from the job_versions history, so every event appears exactly once: a job
that was created, edited or removed produces one version row, and an unchanged job
produces none. Read-only.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.db.models import Company, Job, JobVersion

EVENT_TYPES = ("created", "updated", "reactivated", "removed")


def build_change_summary(
    session: Session,
    *,
    days: int = 7,
    limit: int = 50,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.utcnow()
    since = now - timedelta(days=days)
    active = int(session.scalar(select(func.count()).select_from(Job).where(Job.is_active.is_(True))) or 0)
    inactive = int(session.scalar(select(func.count()).select_from(Job).where(Job.is_active.is_(False))) or 0)

    summary: dict[str, Any] = {
        "window_days": days,
        "since": since.isoformat(),
        "generated_at": now.isoformat(),
        "jobs_active": active,
        "jobs_inactive": inactive,
        "counts": {name: 0 for name in EVENT_TYPES},
        "by_company": [],
        "recent": [],
        "tracking_available": False,
        "note": None,
    }
    has_table = inspect(session.get_bind()).has_table(JobVersion.__tablename__)
    recorded = int(session.scalar(select(func.count()).select_from(JobVersion)) or 0) if has_table else 0
    if recorded == 0:
        summary["note"] = "No change history yet: it starts with the first sync run after change tracking was added."
        return summary
    summary["tracking_available"] = True

    in_window = (JobVersion.captured_at >= since, JobVersion.change_type.in_(EVENT_TYPES))
    for change_type, total in session.execute(
        select(JobVersion.change_type, func.count()).where(*in_window).group_by(JobVersion.change_type)
    ):
        summary["counts"][change_type] = int(total)

    per_company: dict[str, dict[str, int]] = {}
    for company, change_type, total in session.execute(
        select(Company.name, JobVersion.change_type, func.count())
        .join(Job, Job.id == JobVersion.job_id)
        .join(Company, Company.id == Job.company_id)
        .where(*in_window)
        .group_by(Company.name, JobVersion.change_type)
    ):
        per_company.setdefault(company, {name: 0 for name in EVENT_TYPES})[change_type] = int(total)
    summary["by_company"] = [
        {"company": name, **counts, "total": sum(counts.values())}
        for name, counts in sorted(per_company.items(), key=lambda item: -sum(item[1].values()))
    ]

    recent = session.execute(
        select(JobVersion, Job, Company.name)
        .join(Job, Job.id == JobVersion.job_id)
        .join(Company, Company.id == Job.company_id)
        .where(*in_window)
        .order_by(JobVersion.captured_at.desc(), JobVersion.id.desc())
        .limit(limit)
    ).all()
    summary["recent"] = [
        {
            "job_id": job.id,
            "company": company_name,
            "title": version.title,
            "url": job.url,
            "event": version.change_type,
            "changed_fields": version.changed_fields.split(",") if version.changed_fields else [],
            "at": version.captured_at.isoformat(),
        }
        for version, job, company_name in recent
    ]
    return summary
