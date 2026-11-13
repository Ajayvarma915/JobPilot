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
