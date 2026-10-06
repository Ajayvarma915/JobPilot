from app.collectors.google_careers import (
    GoogleCareersCollector,
)
from app.collectors.google_job_details import (
    GoogleJobDetailFetcher,
)


def main() -> None:
    # First get one real current Google job.
    collector = GoogleCareersCollector(
        query="Software Engineer",
        location="Hyderabad",
    )

    jobs = collector.collect()

    if not jobs:
        print("No Google jobs found.")
        return

    job = jobs[0]

    print("SEARCH RESULT")
    print("=" * 70)
    print("Title:", job["title"])
    print("URL  :", job["url"])

    # Now fetch the full job detail page.
    fetcher = GoogleJobDetailFetcher()

    details = fetcher.fetch(
        url=job["url"],
        fallback_title=job["title"],
    )

    print("\n\nFULL JOB DETAIL")
    print("=" * 70)

    print("Title:")
    print(details["title"])

    print("\nSections found:")
    for section_name in details["sections"]:
        print("-", section_name)

    print("\n\nFULL DESCRIPTION")
    print("=" * 70)

    print(details["description"])


if __name__ == "__main__":
    main()