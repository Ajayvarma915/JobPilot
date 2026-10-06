from app.collectors.google_careers import GoogleCareersCollector


REQUIRED_MIN_DESCRIPTION_LENGTH = 200

JD_SECTION_MARKERS = (
    "About The Job",
    "Minimum Qualifications",
    "Preferred Qualifications",
    "Responsibilities",
)


def main():
    collector = GoogleCareersCollector(
        query="Software Engineer",
        location="Hyderabad",
        fetch_details=True,
        max_pages=2,
    )

    jobs = collector.collect()

    print("\n========================================")
    print("Google Pagination + Full JD Test")
    print("========================================")
    print(f"Total unique jobs: {len(jobs)}")

    if not jobs:
        print("\nFAIL: No jobs were collected.")
        raise SystemExit(1)

    passed = 0
    failed = 0

    print("\nValidating jobs...\n")

    for index, job in enumerate(jobs, start=1):
        title = job.get("title", "")
        external_id = job.get("external_id")
        url = job.get("url")
        description = job.get("description") or ""

        checks = {
            "external_id": bool(external_id),
            "url": bool(url),
            "description_length": len(description) >= REQUIRED_MIN_DESCRIPTION_LENGTH,
            "jd_section": any(
                marker.lower() in description.lower()
                for marker in JD_SECTION_MARKERS
            ),
        }

        job_passed = all(checks.values())

        if job_passed:
            passed += 1
            status = "PASS"
        else:
            failed += 1
            status = "FAIL"

        print(f"{index:02d}. [{status}] {title}")
        print(f"    ID: {external_id}")
        print(f"    Description length: {len(description)}")
        print(f"    URL present: {checks['url']}")
        print(f"    JD section present: {checks['jd_section']}")

        if not job_passed:
            print(f"    Checks: {checks}")

        print()

    print("========================================")
    print("Validation Summary")
    print("========================================")
    print(f"Total jobs : {len(jobs)}")
    print(f"Passed     : {passed}")
    print(f"Failed     : {failed}")

    if failed > 0:
        print("\nFAIL: Some jobs did not contain valid full JD data.")
        raise SystemExit(1)

    print("\nSUCCESS: Pagination and full JD enrichment are working correctly.")


if __name__ == "__main__":
    main()