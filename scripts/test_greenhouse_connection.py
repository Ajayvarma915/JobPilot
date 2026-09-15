import requests


def main() -> None:
    board_token = "example"

    url = (
        f"https://boards-api.greenhouse.io/v1/boards/"
        f"{board_token}/jobs"
    )

    response = requests.get(
        url,
        params={"content": "true"},
        timeout=30,
    )

    print("HTTP status:", response.status_code)

    print("\nResponse preview:\n")
    print(response.text[:500])


if __name__ == "__main__":
    main()