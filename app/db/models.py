from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.db.database import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    website: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    careers_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    source_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        nullable=False,
    )

    jobs: Mapped[list["Job"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )


class Job(Base):
    __tablename__ = "jobs"

    __table_args__ = (
        UniqueConstraint(
            "source",
            "external_id",
            name="uq_job_source_external_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )

    external_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    location: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    source: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    experience_level: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    employment_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    posted_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
    )

    first_seen_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        nullable=False,
    )

    last_seen_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        nullable=False,
    )

    company: Mapped["Company"] = relationship(
        back_populates="jobs",
    )



class SourceHealth(Base):
    """Operational history of one registry company's job source.

    The *configured* state lives in data/target_companies.json; this table only
    stores what actually happened when the source was fetched, so a configured
    source can never look verified because of a row here.
    """

    __tablename__ = "source_health"

    company_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(100), nullable=True)

    last_attempt_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(default=0, nullable=False)

    # Counts from the most recent successful fetch.
    raw_jobs: Mapped[int | None] = mapped_column(nullable=True)
    unique_jobs: Mapped[int | None] = mapped_column(nullable=True)
    eligible_jobs: Mapped[int | None] = mapped_column(nullable=True)
    review_jobs: Mapped[int | None] = mapped_column(nullable=True)
    jobs_with_description: Mapped[int | None] = mapped_column(nullable=True)

    # NULL when the connector does not report a per-job detail-fetch status.
    detail_attempted: Mapped[int | None] = mapped_column(nullable=True)
    detail_succeeded: Mapped[int | None] = mapped_column(nullable=True)
    last_enrichment_success_at: Mapped[datetime | None] = mapped_column(nullable=True)

    pagination_status: Mapped[str] = mapped_column(
        String(50), default="not_reported", nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)


class JobVersion(Base):
    """Snapshot of a job at a point where something worth noting happened.

    change_type is one of: baseline (state captured just before the first
    recorded change), created, updated, removed, reactivated. For "updated" the
    changed_fields column lists which tracked fields differ from the previous
    snapshot (title, location, url, description, employment_type).
    """

    __tablename__ = "job_versions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(nullable=False)
    change_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    changed_fields: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    employment_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class AiCacheEntry(Base):
    """Validated result of one local-AI task, kept so the same question is not asked twice.

    Only the validated, structured result is stored (never the prompt or the raw model
    output). The key hashes the task, prompt version, provider, model and the caller's inputs,
    so changing any of them produces a fresh answer.
    """

    __tablename__ = "ai_cache"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    task: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)


class ResumeVersion(Base):
    """One generated tailored resume, kept so versions can be listed per job and re-opened.

    Only metadata, the transparency report and the check results are stored; the files
    themselves live in data/generated_resumes. The master resume is never touched.
    """

    __tablename__ = "resume_versions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    job_title: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    docx_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    pdf_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    audit_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    evidence_count: Mapped[int] = mapped_column(default=0, nullable=False)
    report_json: Mapped[str] = mapped_column(Text, nullable=False)
    evaluation_json: Mapped[str] = mapped_column(Text, nullable=False)
    fabrication_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False, index=True)


class CoverLetterVersion(Base):
    """A cover letter draft. Edits never overwrite: each edit is a new version."""

    __tablename__ = "cover_letter_versions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # template | user_edit
    based_on_version_id: Mapped[int | None] = mapped_column(nullable=True)
    job_title: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    facts_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    saved_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False, index=True)


class EmployerAnswer(Base):
    """A reusable answer to a common employer question, built only from verified facts.

    status: needs_input (a fact is missing or a placeholder remains), draft, or approved.
    Sensitive (salary, work authorization) and company-specific answers can only be approved
    with an explicit confirmation from the user.
    """

    __tablename__ = "employer_answers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    question_key: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    sensitive: Mapped[bool] = mapped_column(default=False, nullable=False)
    company_specific: Mapped[bool] = mapped_column(default=False, nullable=False)
    job_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    facts_used: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
