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
            f"Found {len(jobs)} jobs in database.\n"
        )

        passed = 0
        failed = 0

        for index, job in enumerate(
            jobs,
            start=1,
        ):
            description = (
                job.description or ""
            ).strip()

            has_external_id = bool(
                job.external_id
            )

            has_url = bool(job.url)

            has_description = (
                len(description) >= 200
            )

            # A full Google JD should normally contain
            # at least one of these major sections.
            lower_description = (
                description.lower()
            )

            has_jd_section = any(
                section in lower_description
                for section in (
                    "minimum qualifications",
                    "preferred qualifications",
                    "responsibilities",
                    "about the job",
                )
            )

            valid = (
                has_external_id
                and has_url
                and has_description
                and has_jd_section
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
                    f"      External ID: "
                    f"{has_external_id}"
                )
                print(
                    f"      URL: "
                    f"{has_url}"
                )
                print(
                    f"      JD length: "
                    f"{len(description)}"
                )
                print(
                    f"      JD sections: "
                    f"{has_jd_section}"
                )

        print(
            "\n========================================"
        )
        print("Database JD Verification")
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