from app.collectors.google_careers import GoogleCareersCollector


def main() -> None:
    collector = GoogleCareersCollector(
        query="Software Engineer",
        location="Hyderabad",
        fetch_details=True,
    )

    jobs = collector.collect()

    print(f"Found {len(jobs)} jobs.\n")

    for index, job in enumerate(jobs[:10], start=1):
        print("=" * 70)
        print(f"JOB {index}")
        print("=" * 70)

        print("Company    :", job["company"])
        print("Title      :", job["title"])
        print("Location   :", job["location"])
        print("Experience :", job["experience_level"])
        print("URL        :", job["url"])

        print("\nDescription:")
        print(job["description"][:2000])
        print()


if __name__ == "__main__":
    main()