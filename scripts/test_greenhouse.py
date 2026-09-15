from app.collectors.greenhouse import GreenhouseCollector


def main() -> None:
    collector = GreenhouseCollector(
        board_token="GOOGLE",
        company_name="Test Company",
    )

    jobs = collector.collect()

    print(f"Found {len(jobs)} jobs.\n")

    for job in jobs[:5]:
        print("=" * 60)
        print("Company :", job["company"])
        print("Title   :", job["title"])
        print("Location:", job["location"])
        print("URL     :", job["url"])
        print()


if __name__ == "__main__":
    main()