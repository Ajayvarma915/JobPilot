from app.collectors.google_careers import GoogleCareersCollector


def main() -> None:
    collector = GoogleCareersCollector(
        query="Software Engineer",
        location="Hyderabad",
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
        print("Experience :", job["experience"])
        print("URL        :", job["url"])

        description = job["description"]

        print("\nDescription:")
        print(description[:1000])
        print()


if __name__ == "__main__":
    main()