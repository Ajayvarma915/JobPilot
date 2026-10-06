from sqlalchemy import func, select

from app.db.database import SessionLocal
from app.db.models import Company, Job


def main() -> None:
    db = SessionLocal()

    try:
        job_count = db.scalar(
            select(func.count(Job.id))
        )

        company_count = db.scalar(
            select(func.count(Company.id))
        )

        print(
            f"Companies: {company_count}"
        )

        print(
            f"Jobs     : {job_count}"
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()