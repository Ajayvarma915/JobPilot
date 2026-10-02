from sqlalchemy.exc import IntegrityError

from app.db.database import SessionLocal
from app.db.models import Company, Job


def main() -> None:
    db = SessionLocal()

    try:
        company = Company(
            name="Google",
            website="https://www.google.com",
            careers_url=(
                "https://www.google.com/about/careers/"
                "applications/jobs/results/"
            ),
            source_type="google_careers",
        )

        db.add(company)
        db.commit()
        db.refresh(company)

        job_1 = Job(
            company_id=company.id,
            external_id="12345",
            title="Software Engineer",
            location="Hyderabad",
            url="https://example.com/job/12345",
            description="Test job",
            source="google_careers",
        )

        db.add(job_1)
        db.commit()

        print("First job inserted successfully.")

        job_2 = Job(
            company_id=company.id,
            external_id="12345",
            title="Software Engineer",
            location="Hyderabad",
            url="https://example.com/job/12345",
            description="Same job again",
            source="google_careers",
        )

        db.add(job_2)

        try:
            db.commit()

            print(
                "ERROR: duplicate job was accepted."
            )

        except IntegrityError:
            db.rollback()

            print(
                "SUCCESS: duplicate job was rejected."
            )

    finally:
        db.close()


if __name__ == "__main__":
    main()