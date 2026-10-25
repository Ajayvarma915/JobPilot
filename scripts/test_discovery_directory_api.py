from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import app


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_company_directory(client: TestClient) -> None:
    response = client.get("/api/companies", params={"limit": 1000})

    check(
        response.status_code == 200,
        f"Company endpoint failed: {response.text}",
    )

    data = response.json()
    companies = data["items"]

    check(isinstance(companies, list), "Company items must be a list.")

    if companies:
        company = companies[0]

        check(
            isinstance(company.get("id"), int),
            "Company ID should be an integer.",
        )
        check(
            bool(company.get("name")),
            "Company name is missing.",
        )
        check(
            company["active_job_count"] <= company["job_count"],
            "Active job count cannot exceed total job count.",
        )
        check(
            isinstance(company.get("source_types"), list),
            "Company source_types should be a list.",
        )

    search_response = client.get(
        "/api/companies",
        params={"q": "google", "limit": 1000},
    )

    check(
        search_response.status_code == 200,
        "Searchable company endpoint failed.",
    )

    for company in search_response.json()["items"]:
        check(
            "google" in company["name"].casefold(),
            "Company search returned a non-matching company.",
        )


def test_location_directory(client: TestClient) -> None:
    response = client.get("/api/locations", params={"limit": 1000})

    check(
        response.status_code == 200,
        f"Location endpoint failed: {response.text}",
    )

    data = response.json()
    locations = data["items"]

    check(isinstance(locations, list), "Location items must be a list.")

    seen_cities: set[str] = set()

    for location in locations:
        city = location.get("city")
        value = location.get("value")
        count = location.get("job_count")

        check(bool(city), "Location city is missing.")
        check(value == city, "Location value should match the city label.")
        check(
            isinstance(count, int) and count > 0,
            "Location job count must be a positive integer.",
        )

        normalized = city.strip().casefold()

        check(
            normalized not in seen_cities,
            f"Duplicate location option found: {city}",
        )
        seen_cities.add(normalized)

    india_options = [
        item for item in locations if item["value"].casefold() == "india"
    ]
    check(
        len(india_options) == 1,
        "Location directory should provide one India country option.",
    )
    check(
        india_options[0]["job_count"] > 0,
        "India option should count listings that explicitly identify India.",
    )

    hyderabad_response = client.get(
        "/api/locations",
        params={"q": "hyderabad", "limit": 1000},
    )

    check(
        hyderabad_response.status_code == 200,
        "Searching the location directory failed.",
    )

    for location in hyderabad_response.json()["items"]:
        check(
            "hyderabad" in location["city"].casefold(),
            "Location search returned a non-matching city.",
        )


def test_job_title_suggestions(client: TestClient) -> None:
    response = client.get(
        "/api/job-suggestions",
        params={"q": "software", "limit": 8},
    )

    check(
        response.status_code == 200,
        f"Job suggestion endpoint failed: {response.text}",
    )

    data = response.json()
    suggestions = data["items"]

    check(
        isinstance(suggestions, list),
        "Suggestion items must be a list.",
    )
    check(
        len(suggestions) <= 8,
        "Suggestion endpoint exceeded the requested limit.",
    )

    for suggestion in suggestions:
        check(
            bool(suggestion.get("title")),
            "Suggested job title is missing.",
        )
        check(
            isinstance(suggestion.get("count"), int)
            and suggestion["count"] > 0,
            "Suggestion count must be positive.",
        )
        check(
            isinstance(suggestion.get("companies"), list),
            "Suggestion companies must be a list.",
        )
        check(
            "software" in suggestion["title"].casefold(),
            "A returned suggestion does not match the query.",
        )

    short_query = client.get(
        "/api/job-suggestions",
        params={"q": "s"},
    )

    check(
        short_query.status_code == 200,
        "Short-query suggestion response failed.",
    )
    check(
        short_query.json()["items"] == [],
        "Queries shorter than two characters should return no suggestions.",
    )


def main() -> int:
    tests = [
        ("Searchable company directory", test_company_directory),
        ("Searchable location directory", test_location_directory),
        ("Job title autocomplete", test_job_title_suggestions),
    ]

    print("=" * 68)
    print("JobPilot Discovery Directory API Tests")
    print("=" * 68)

    passed = 0
    failed = 0

    with TestClient(app) as client:
        for number, (name, test) in enumerate(tests, start=1):
            try:
                test(client)
                passed += 1
                print(f"Test {number}: PASS - {name}")
            except Exception as exc:
                failed += 1
                print(
                    f"Test {number}: FAIL - {name}\n"
                    f"  {type(exc).__name__}: {exc}"
                )

    print(f"\nUnit tests: {passed} passed, {failed} failed")

    if failed:
        print("FAILURE: Discovery directory tests failed.")
        return 1

    print("SUCCESS: Discovery directory tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())