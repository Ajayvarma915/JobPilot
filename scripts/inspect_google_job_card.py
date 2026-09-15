import re

import requests
from bs4 import BeautifulSoup


URL = "https://www.google.com/about/careers/applications/jobs/results/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0.0.0 Safari/537.36"
    )
}


def main() -> None:
    response = requests.get(
        URL,
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Find the first visible occurrence of a Software Engineer title.
    target = soup.find(
        string=re.compile(
            r"Software Engineer",
            re.IGNORECASE,
        )
    )

    if target is None:
        print("Could not find a Software Engineer title.")
        return

    print("Found title:")
    print(target.strip())

    print("\n--- Parent element ---")

    parent = target.parent

    if parent is not None:
        print(parent.name)
        print(parent.attrs)

    print("\n--- Parent HTML ---")

    if parent is not None:
        print(parent.prettify()[:10000])

    print("\n--- Ancestor chain ---")

    current = target.parent

    for level in range(8):
        if current is None:
            break

        print(
            f"\nLEVEL {level}: "
            f"<{current.name}> "
            f"attrs={current.attrs}"
        )

        current = current.parent


if __name__ == "__main__":
    main()