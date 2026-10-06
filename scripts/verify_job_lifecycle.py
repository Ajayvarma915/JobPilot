from __future__ import annotations

from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import Job


def main() -> None:
    db = SessionLocal()

    try:
        jobs = db.scalars(
            select(Job)
            .order_by(Job.id)
        ).all()

        print(
            f"Found {len(jobs)} jobs.\n"
        )

        passed = 0
        failed = 0

        for index, job in enumerate(
            jobs,
            start=1,
        ):
            valid = (
                job.first_seen_at is not None
                and job.last_seen_at is not None
                and job.is_active is True
            )

            if valid:
                passed += 1
                status = "PASS"
            else:
                failed += 1
                status = "FAIL"

            print(
                f"{status} | "
                f"{index:02d} | "
                f"{job.title}"
            )

            if not valid:
                print(
                    "      first_seen_at:",
                    job.first_seen_at,
                )

                print(
                    "      last_seen_at:",
                    job.last_seen_at,
                )

                print(
                    "      is_active:",
                    job.is_active,
                )

        print(
            "\n========================================"
        )
        print("Job Lifecycle Verification")
        print(
            "========================================"
        )
        print(f"Total : {len(jobs)}")
        print(f"Pass  : {passed}")
        print(f"Fail  : {failed}")

    finally:
        db.close()


if __name__ == "__main__":
    main()