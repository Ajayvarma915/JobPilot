from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import Job


def main() -> None:
    db = SessionLocal()

    try:
        jobs = db.scalars(
            select(Job)
        ).all()

        print(f"Found {len(jobs)} job(s).\n")

        for job in jobs:
            print(
                f"[{job.id}] "
                f"{job.company} | "
                f"{job.title} | "
                f"{job.location}"
            )

    finally:
        db.close()


if __name__ == "__main__":
    main()
    