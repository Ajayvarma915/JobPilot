from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Company, Job, JobReview, JobVersion

# Fields whose change counts as a real change to a posting.
TRACKED_FIELDS = ("title", "location", "url", "description", "employment_type")

CREATED = "created"
UPDATED = "updated"
UNCHANGED = "unchanged"
REACTIVATED = "reactivated"


@dataclass
class UpsertResult:
    job: Job
    status: str  # created / updated / unchanged / reactivated
    changed_fields: list[str] = field(default_factory=list)

    @property
    def created(self) -> bool:
        return self.status == CREATED


def content_hash(values: dict[str, Any]) -> str:
    """Stable hash of the tracked fields (whitespace-insensitive)."""
    parts = []
    for name in TRACKED_FIELDS:
        text = " ".join(str(values.get(name) or "").split())
        parts.append(f"{name}={text}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def ensure_support_tables(bind) -> None:
    """Create the additive tables (job history, review queue) if an older database lacks them.

    Must run BEFORE a session starts writing: creating a table from another connection in the middle
    of a write transaction makes SQLite answer "database is locked" (found in a sandbox sync).
    """
    JobVersion.__table__.create(bind=bind, checkfirst=True)
    JobReview.__table__.create(bind=bind, checkfirst=True)


class JobRepository:
    """Database operations for companies and jobs."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self._versions_ready = False
        if not hasattr(db, "get_bind"):
            return  # a test double
        ensure_support_tables(db.get_bind())

    # -- schema ---------------------------------------------------------------
    def _ensure_versions_table(self) -> None:
        """Create job_versions on first use (additive, idempotent)."""
        if not self._versions_ready:
            JobVersion.__table__.create(bind=self.db.get_bind(), checkfirst=True)
            self._versions_ready = True

    # -- review queue ---------------------------------------------------------
    def set_review(self, job: Job, flags: Iterable[str]) -> None:
        """Hold this job for your review. A decision you already made is kept as it is."""
        JobReview.__table__.create(bind=self.db.get_bind(), checkfirst=True)
        text = ";".join(dict.fromkeys(flag for flag in flags if flag))
        row = self.db.get(JobReview, job.id)
        if row is None:
            self.db.add(JobReview(job_id=job.id, status="pending", flags=text))
        elif row.status == "pending":
            row.flags = text
        self.db.flush()

    def clear_pending_review(self, job: Job) -> None:
        """The job now passes every rule on its own, so it no longer needs your review."""
        JobReview.__table__.create(bind=self.db.get_bind(), checkfirst=True)
        row = self.db.get(JobReview, job.id)
        if row is not None and row.status == "pending":
            self.db.delete(row)
            self.db.flush()

    # -- companies ------------------------------------------------------------
    def get_or_create_company(
        self,
        name: str,
        website: str | None = None,
        careers_url: str | None = None,
        source_type: str | None = None,
    ) -> Company:
        company = self.db.scalar(select(Company).where(Company.name == name))
        if company is not None:
            return company

        company = Company(
            name=name,
            website=website,
            careers_url=careers_url,
            source_type=source_type,
        )
        self.db.add(company)
        self.db.flush()
        return company

    def get_company(self, name: str) -> Company | None:
        return self.db.scalar(select(Company).where(Company.name == name))

    # -- jobs -----------------------------------------------------------------
    def get_job(
        self,
        source: str,
        external_id: str | None,
        url: str | None = None,
    ) -> Job | None:
        """Find an existing job by source + external_id, falling back to source + URL."""
        if external_id:
            job = self.db.scalar(
                select(Job).where(Job.source == source, Job.external_id == external_id)
            )
            if job is not None:
                return job
        if url:
            return self.db.scalar(select(Job).where(Job.source == source, Job.url == url))
        return None

    @staticmethod
    def _location_value(job_data: dict[str, Any]) -> str | None:
        location = job_data.get("location", [])
        if isinstance(location, list):
            return "; ".join(location)
        return location

    def _snapshot_values(self, job: Job) -> dict[str, Any]:
        return {name: getattr(job, name) for name in TRACKED_FIELDS}

    def _record_version(
        self,
        job: Job,
        change_type: str,
        changed_fields: Iterable[str] = (),
        now: datetime | None = None,
    ) -> JobVersion:
        self._ensure_versions_table()
        next_no = int(
            self.db.scalar(
                select(func.coalesce(func.max(JobVersion.version_no), 0)).where(JobVersion.job_id == job.id)
            )
            or 0
        ) + 1
        values = self._snapshot_values(job)
        version = JobVersion(
            job_id=job.id,
            version_no=next_no,
            change_type=change_type,
            changed_fields=",".join(changed_fields) or None,
            content_hash=content_hash(values),
            captured_at=now or datetime.utcnow(),
            title=values["title"] or "",
            location=values["location"],
            url=values["url"] or "",
            employment_type=values["employment_type"],
            description=values["description"] or "",
        )
        self.db.add(version)
        # Sessions here run with autoflush off; flush so numbering and the
        # "has versions" checks see this row immediately.
        self.db.flush()
        return version

    def _has_versions(self, job: Job) -> bool:
        self._ensure_versions_table()
        return self.db.scalar(select(func.count()).select_from(JobVersion).where(JobVersion.job_id == job.id)) > 0

    def upsert_job_detailed(self, company: Company, job_data: dict[str, Any]) -> UpsertResult:
        """Insert or update a job and report exactly what happened.

        - created:     new job (version 1 recorded)
        - updated:     a tracked field changed (previous state kept as a version)
        - reactivated: the job had been marked removed and is posted again
        - unchanged:   nothing tracked changed; only last_seen_at is refreshed
        """
        source = job_data["source"]
        external_id = job_data.get("external_id")
        url = job_data.get("url")
        now = datetime.utcnow()

        incoming = {
            "title": job_data["title"],
            "location": self._location_value(job_data),
            "url": url,
            "description": job_data.get("description", ""),
            "employment_type": job_data.get("employment_type"),
        }

        existing = self.get_job(source=source, external_id=external_id, url=url)

        if existing is None:
            job = Job(
                company_id=company.id,
                external_id=external_id,
                title=incoming["title"],
                location=incoming["location"],
                url=url,
                description=incoming["description"],
                source=source,
                experience_level=job_data.get("experience_level"),
                employment_type=incoming["employment_type"],
                posted_at=job_data.get("posted_at"),
                first_seen_at=now,
                last_seen_at=now,
                is_active=True,
            )
            self.db.add(job)
            self.db.flush()
            self._record_version(job, CREATED, now=now)
            return UpsertResult(job, CREATED)

        changed = [
            name for name in TRACKED_FIELDS
            if " ".join(str(getattr(existing, name) or "").split()) != " ".join(str(incoming[name] or "").split())
        ]
        was_inactive = not existing.is_active

        if changed and not self._has_versions(existing):
            # Jobs stored before version tracking existed: keep their old state as the baseline.
            self._record_version(existing, "baseline", now=existing.last_seen_at)

        if changed:
            for name in changed:
                setattr(existing, name, incoming[name])

        # Untracked fields follow the source but never count as a change.
        existing.company_id = company.id
        existing.external_id = external_id
        existing.experience_level = job_data.get("experience_level")
        existing.posted_at = job_data.get("posted_at")
        existing.source = source
        existing.last_seen_at = now
        existing.is_active = True
        self.db.flush()

        if changed:
            self._record_version(existing, REACTIVATED if was_inactive else UPDATED, changed, now=now)
            return UpsertResult(existing, REACTIVATED if was_inactive else UPDATED, changed)
        if was_inactive:
            self._record_version(existing, REACTIVATED, now=now)
            return UpsertResult(existing, REACTIVATED)
        return UpsertResult(existing, UNCHANGED)

    def upsert_job(self, company: Company, job_data: dict[str, Any]) -> tuple[Job, bool]:
        """Backward-compatible wrapper: returns (job, created)."""
        result = self.upsert_job_detailed(company, job_data)
        return result.job, result.created

    # -- single-job lifecycle -------------------------------------------------
    def confirm_open(self, job: Job) -> None:
        """The source still lists this job: refresh the time and reactivate it if needed."""
        now = datetime.utcnow()
        job.last_seen_at = now
        if not job.is_active:
            job.is_active = True
            self.db.flush()
            self._record_version(job, REACTIVATED, now=now)
        self.db.flush()

    def mark_closed(self, job: Job) -> None:
        """The source no longer lists this job: keep it, but mark it closed (with history)."""
        if not job.is_active:
            return
        if not self._has_versions(job):
            self._record_version(job, "baseline", now=job.last_seen_at)
        job.is_active = False
        self.db.flush()
        self._record_version(job, "removed")

    def mark_source_missing_inactive(self, source: str, seen_external_ids: set[str]) -> list[Job]:
        """For a feed that mixes many employers: close this source's jobs that are no longer listed."""
        now = datetime.utcnow()
        removed: list[Job] = []
        for job in self.db.scalars(select(Job).where(Job.source == source, Job.is_active.is_(True))).all():
            if job.external_id is not None and job.external_id in seen_external_ids:
                continue
            if not self._has_versions(job):
                self._record_version(job, "baseline", now=job.last_seen_at)
            job.is_active = False
            self.db.flush()
            self._record_version(job, "removed", now=now)
            removed.append(job)
        return removed

    def active_source_count(self, source: str) -> int:
        return int(self.db.scalar(select(func.count()).select_from(Job).where(Job.source == source, Job.is_active.is_(True))) or 0)

    # -- removal detection ----------------------------------------------------
    def active_job_count(self, company: Company, sources: Iterable[str]) -> int:
        return int(
            self.db.scalar(
                select(func.count()).select_from(Job).where(
                    Job.company_id == company.id, Job.source.in_(list(sources)), Job.is_active.is_(True)
                )
            )
            or 0
        )

    def mark_missing_inactive(
        self,
        company: Company,
        sources: Iterable[str],
        seen_external_ids: set[str],
    ) -> list[Job]:
        """Mark active jobs that are no longer on the source as removed.

        The caller decides whether the fetch was complete enough to trust.
        """
        now = datetime.utcnow()
        candidates = self.db.scalars(
            select(Job).where(
                Job.company_id == company.id, Job.source.in_(list(sources)), Job.is_active.is_(True)
            )
        ).all()
        removed: list[Job] = []
        for job in candidates:
            if job.external_id is not None and job.external_id in seen_external_ids:
                continue
            if not self._has_versions(job):
                self._record_version(job, "baseline", now=job.last_seen_at)
            job.is_active = False
            self.db.flush()
            self._record_version(job, "removed", now=now)
            removed.append(job)
        return removed
