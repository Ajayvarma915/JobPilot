from app.collectors.google_careers import (
    GoogleCareersCollector,
)


def main() -> None:
    collector = GoogleCareersCollector(
        query="Software Engineer",
        location="Hyderabad",
        fetch_details=True,
    )

    jobs = collector.collect()

    print(
        f"\nCollected {len(jobs)} enriched jobs.\n"
    )

    successful = 0
    failed = 0

    for index, job in enumerate(
        jobs,
        start=1,
    ):
        description = job.get(
            "description",
            "",
        )

        sections = job.get(
            "detail_sections",
            {},
        )

        has_url = bool(job.get("url"))
        has_external_id = bool(
            job.get("external_id")
        )
        has_description = len(
            description.strip()
        ) > 200
        has_sections = bool(sections)

        valid = (
            has_url
            and has_external_id
            and has_description
            and has_sections
        )

        if valid:
            successful += 1
            status = "PASS"
        else:
            failed += 1
            status = "FAIL"

        print(
            f"{status} | "
            f"{index:02d} | "
            f"{job['title']}"
        )

        if not valid:
            print(
                f"      URL: {has_url}"
            )
            print(
                f"      ID: {has_external_id}"
            )
            print(
                f"      JD: {has_description}"
            )
            print(
                f"      Sections: {has_sections}"
            )

    print("\n==============================")
    print("Google JD Verification")
    print("==============================")
    print(f"Total : {len(jobs)}")
    print(f"Pass  : {successful}")
    print(f"Fail  : {failed}")


if __name__ == "__main__":
    main()