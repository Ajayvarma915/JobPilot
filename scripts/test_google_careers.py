import requests


URL = "https://www.google.com/about/careers/applications/jobs/results/"


def main() -> None:
    response = requests.get(
        URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/153.0.0.0 Safari/537.36"
            )
        },
        timeout=30,
    )

    print("HTTP status:", response.status_code)
    print("Content-Type:", response.headers.get("content-type"))
    print("Response length:", len(response.text))

    print("\nFirst 500 characters:\n")
    print(response.text[:500])


if __name__ == "__main__":
    main()