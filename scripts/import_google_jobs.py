from __future__ import annotations

from app.collectors.google_careers import GoogleCareersCollector
from app.db.database import SessionLocal
from app.db.job_repository import JobRepository


QUERY = "Software Engineer"
LOCATION = "Hyderabad"
MAX_PAGES = 2


def main() -> None:
    print("========================================")
    print("Google Careers Database Import")
    print("========================================")
    print(f"Query      : {QUERY}")
    print(f"Location   : {LOCATION}")
    print(f"Max pages  : {MAX_PAGES}")
    print("Full JDs   : enabled")
    print()

    collector = GoogleCareersCollector(
        query=QUERY,
        location=LOCATION,
        fetch_details=True,
        max_pages=MAX_PAGES,
    )

    print("Starting collection...\n")

    jobs = collector.collect()

    print()
    print("========================================")
    print("Collection Complete")
    print("========================================")
    print(f"Collected : {len(jobs)}")

    if not jobs:
        print("No jobs were collected.")
        return

    db = SessionLocal()

    created_count = 0
    updated_count = 0
    short_jds = 0

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

        for index, job_data in enumerate(
            jobs,
            start=1,
        ):
            description = job_data.get(
                "description",
                "",
            )

            if len(description) < 200:
                short_jds += 1

                print(
                    f"WARNING: Short JD "
                    f"for job {index}/{len(jobs)}: "
                    f"{job_data.get('title')}"
                )

            job, created = repository.upsert_job(
                company=company,
                job_data=job_data,
            )

            if created:
                created_count += 1

                print(
                    f"{index:02d}/{len(jobs):02d} "
                    f"[INSERTED] "
                    f"{job.title}"
                )

            else:
                updated_count += 1

                print(
                    f"{index:02d}/{len(jobs):02d} "
                    f"[UPDATED] "
                    f"{job.title}"
                )

        db.commit()

        print()
        print("========================================")
        print("Google Import Summary")
        print("========================================")
        print(f"Collected : {len(jobs)}")
        print(f"Inserted  : {created_count}")
        print(f"Updated   : {updated_count}")
        print(f"Short JDs : {short_jds}")

        print()
        print(
            "SUCCESS: Google jobs synchronized "
            "with the database."
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()