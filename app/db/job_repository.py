from __future__ import annotations

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

    def create_job(
        self,
        company: Company,
        job_data: dict[str, Any],
    ) -> Job:
        job = Job(
            company_id=company.id,
            external_id=job_data.get("external_id"),
            title=job_data["title"],
            location="; ".join(
                job_data.get("location", [])
            ),
            url=job_data["url"],
            description=job_data.get(
                "description",
                "",
            ),
            source=job_data["source"],
            experience_level=job_data.get(
                "experience_level"
            ),
            employment_type=job_data.get(
                "employment_type"
            ),
            posted_at=job_data.get("posted_at"),
        )

        self.db.add(job)

        return job