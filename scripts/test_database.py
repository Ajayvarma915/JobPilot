from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import Company, Job


def main() -> None:
    db = SessionLocal()

    try:
        google = Company(
            name="Google",
            website="https://www.google.com",
            careers_url=(
                "https://www.google.com/about/careers/"
                "applications/jobs/results/"
            ),
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
            url=(
                "https://www.google.com/about/careers/"
                "applications/jobs/results/"
                "100397577702122182-"
                "software-engineer-chrome-networking-security"
            ),
            description=(
                "Bachelor’s degree or equivalent practical experience.\n"
                "2 years of experience with software development in C++."
            ),
            source="google_careers",
            experience_level="Mid",
        )

        db.add(job)
        db.commit()
        db.refresh(job)

        print("Company created:")
        print(f"  ID:   {google.id}")
        print(f"  Name: {google.name}")

        print("\nJob created:")
        print(f"  ID:       {job.id}")
        print(f"  External: {job.external_id}")
        print(f"  Title:    {job.title}")
        print(f"  Company:  {job.company.name}")

        print("\nDatabase read test:")

        jobs = db.scalars(
            select(Job)
        ).all()

        for item in jobs:
            print(
                f"[{item.id}] "
                f"{item.company.name} | "
                f"{item.title} | "
                f"{item.location}"
            )

    finally:
        db.close()


if __name__ == "__main__":
    main()