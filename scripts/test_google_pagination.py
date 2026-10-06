from app.collectors.google_careers import (
    GoogleCareersCollector,
)


def main() -> None:
    collector = GoogleCareersCollector(
        query="Software Engineer",
        location="Hyderabad",
        fetch_details=False,
        max_pages=2,
    )

    jobs = collector.collect()

    print("\n========================================")
    print("Google Pagination Test")
    print("========================================")

    print(
        f"Total unique jobs: {len(jobs)}"
    )

    print("\nJobs:\n")

    for index, job in enumerate(
        jobs,
        start=1,
    ):
        print(
            f"{index:02d}. "
            f"{job['title']}"
        )

        print(
            f"    ID: "
            f"{job['external_id']}"
        )

        print(
            f"    Location: "
            f"{job['location']}"
        )

        print(
            f"    URL: "
            f"{job['url']}"
        )


if __name__ == "__main__":
    main()