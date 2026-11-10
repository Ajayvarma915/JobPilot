"""Duplicate-job constraint test.

Uses a temporary SQLite file (JOBPILOT_DATABASE_PATH) so the real jobpilot.db
is never modified and the test is repeatable.
"""
import os
import sys
import tempfile
from pathlib import Path


def main() -> int:
    with tempfile.TemporaryDirectory() as directory:
        temp_db = Path(directory) / "test_jobpilot.db"
        os.environ["JOBPILOT_DATABASE_PATH"] = str(temp_db)

        from sqlalchemy.exc import IntegrityError

        from app.db.database import Base, DATABASE_PATH, SessionLocal, engine
        from app.db.models import Company, Job

        assert Path(DATABASE_PATH) == temp_db.resolve(), "Test must use the temporary database"
        Base.metadata.create_all(bind=engine)

        db = SessionLocal()
        try:
            company = Company(
                name="Google",
                website="https://www.google.com",
                careers_url="https://www.google.com/about/careers/applications/jobs/results/",
                source_type="google_careers",
            )
            db.add(company)
            db.commit()
            db.refresh(company)

            def make_job(description: str) -> Job:
                return Job(
                    company_id=company.id,
                    external_id="12345",
                    title="Software Engineer",
                    location="Hyderabad",
                    url="https://example.com/job/12345",
                    description=description,
                    source="google_careers",
                )

            db.add(make_job("Test job"))
            db.commit()

            db.add(make_job("Same job again"))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
            else:
                raise AssertionError("A duplicate (company, source, external_id) job was accepted")

            remaining = db.query(Job).count()
            assert remaining == 1, f"Expected one stored job after duplicate rejection, found {remaining}"
            print("PASS - duplicate job was rejected and only one row remains")
        finally:
            db.close()
            engine.dispose()

    return 0


if __name__ == "__main__":
    sys.exit(main())
