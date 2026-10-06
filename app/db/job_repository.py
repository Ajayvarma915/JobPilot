from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Company, Job


class JobRepository:
    """Database operations for companies and jobs."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_or_create_company(
        self,
        name: str,
        website: str | None = None,
        careers_url: str | None = None,
        source_type: str | None = None,
    ) -> Company:
        company = self.db.scalar(
            select(Company).where(
                Company.name == name
            )
        )

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

    def get_job(
        self,
        source: str,
        external_id: str | None,
        url: str | None = None,
    ) -> Job | None:
        """
        Find an existing job.

        Primary identity:
            source + external_id

        Fallback:
            source + URL
        """

        if external_id:
            job = self.db.scalar(
                select(Job).where(
                    Job.source == source,
                    Job.external_id == external_id,
                )
            )

            if job is not None:
                return job

        if url:
            return self.db.scalar(
                select(Job).where(
                    Job.source == source,
                    Job.url == url,
                )
            )

        return None

    def upsert_job(
        self,
        company: Company,
        job_data: dict[str, Any],
    ) -> tuple[Job, bool]:
        """
        Insert a new job or update an existing job.

        Returns:
            (job, created)

        created=True:
            A new job was inserted.

        created=False:
            An existing job was updated.
        """

        source = job_data["source"]
        external_id = job_data.get(
            "external_id"
        )
        url = job_data.get("url")

        now = datetime.utcnow()

        existing_job = self.get_job(
            source=source,
            external_id=external_id,
            url=url,
        )

        location = job_data.get(
            "location",
            [],
        )

        if isinstance(location, list):
            location_value = "; ".join(
                location
            )
        else:
            location_value = location

        if existing_job is not None:
            existing_job.company_id = (
                company.id
            )

            existing_job.external_id = (
                external_id
            )

            existing_job.title = (
                job_data["title"]
            )

            existing_job.location = (
                location_value
            )

            existing_job.url = url

            existing_job.description = (
                job_data.get(
                    "description",
                    "",
                )
            )

            existing_job.source = source

            existing_job.experience_level = (
                job_data.get(
                    "experience_level"
                )
            )

            existing_job.employment_type = (
                job_data.get(
                    "employment_type"
                )
            )

            existing_job.posted_at = (
                job_data.get(
                    "posted_at"
                )
            )

            # Lifecycle tracking.
            existing_job.last_seen_at = now
            existing_job.is_active = True

            self.db.flush()

            return existing_job, False

        new_job = Job(
            company_id=company.id,
            external_id=external_id,
            title=job_data["title"],
            location=location_value,
            url=url,
            description=job_data.get(
                "description",
                "",
            ),
            source=source,
            experience_level=job_data.get(
                "experience_level"
            ),
            employment_type=job_data.get(
                "employment_type"
            ),
            posted_at=job_data.get(
                "posted_at"
            ),
            first_seen_at=now,
            last_seen_at=now,
            is_active=True,
        )

        self.db.add(new_job)
        self.db.flush()

        return new_job, True