"""Database round-trip test.

Runs against a temporary SQLite file selected through JOBPILOT_DATABASE_PATH so
it never touches the real jobpilot.db and can be re-run any number of times.
"""
import os
import sys
import tempfile
from pathlib import Path


def main() -> int:
    with tempfile.TemporaryDirectory() as directory:
        temp_db = Path(directory) / "test_jobpilot.db"
        os.environ["JOBPILOT_DATABASE_PATH"] = str(temp_db)

        # Imported only after the override is set so the engine binds to the temp file.
        from sqlalchemy import select

        from app.db.database import Base, DATABASE_PATH, SessionLocal, engine
        from app.db.models import Company, Job

        assert Path(DATABASE_PATH) == temp_db.resolve(), "Test must use the temporary database"
        Base.metadata.create_all(bind=engine)

        db = SessionLocal()
        try:
            google = Company(
                name="Google",
                website="https://www.google.com",
                careers_url="https://www.google.com/about/careers/applications/jobs/results/",
                source_type="google_careers",
            )
            db.add(google)
            db.commit()
            db.refresh(google)

            job = Job(
                company_id=google.id,
                external_id="100397577702122182",
                title="Software Engineer, Chrome Networking Security",
                location="Mountain View, CA, USA; Cambridge, MA, USA",
                url="https://www.google.com/about/careers/applications/jobs/results/100397577702122182",
                description=(
                    "Bachelor's degree or equivalent practical experience.\n"
                    "2 years of experience with software development in C++."
                ),
                source="google_careers",
                experience_level="Mid",
            )
            db.add(job)
            db.commit()
            db.refresh(job)

            jobs = db.scalars(select(Job)).all()
            assert len(jobs) == 1, f"Expected exactly one job in the temp DB, found {len(jobs)}"
            assert jobs[0].company.name == "Google"
            assert jobs[0].external_id == "100397577702122182"
            print("PASS - company and job round-trip through the temporary database")
        finally:
            db.close()
            engine.dispose()

    return 0


if __name__ == "__main__":
    sys.exit(main())
