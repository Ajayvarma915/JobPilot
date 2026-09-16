from app.collectors.google_careers import (
    GoogleCareersCollector,
)
from app.db.database import SessionLocal
from app.db.job_repository import JobRepository


def main() -> None:
    collector = GoogleCareersCollector(
        query="Software Engineer",
        location="Hyderabad",
    )

    jobs = collector.collect()

    print(f"Collected {len(jobs)} jobs from Google.\n")

    db = SessionLocal()

    try:
        repository = JobRepository(db)

        company = repository.get_or_create_company(
            name="Google",
            website="https://www.google.com",
            careers_url=(
                "https://www.google.com/about/careers/"
                "applications/jobs/results/"
            ),
            source_type="google_careers",
        )

        for job_data in jobs:
            job = repository.create_job(
                company=company,
                job_data=job_data,
            )

            print(
                f"Prepared: "
                f"{job.title}"
            )

        db.commit()

        print(
            "\nSuccessfully imported "
            f"{len(jobs)} jobs."
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()