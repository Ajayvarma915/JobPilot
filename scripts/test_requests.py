import requests


def main() -> None:
    response = requests.get(
        "https://example.com",
        timeout=10,
    )

    response.raise_for_status()

    print("HTTP status:", response.status_code)
    print("Internet request successful!")


if __name__ == "__main__":
    main()