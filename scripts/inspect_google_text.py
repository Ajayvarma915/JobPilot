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

    # Remove scripts/styles so we can inspect visible-ish text.
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text("\n", strip=True)

    # Collapse excessive blank lines.
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    print(f"Total text lines: {len(lines)}\n")

    print("First 200 useful lines:\n")

    for i, line in enumerate(lines[:200], start=1):
        print(f"{i:03}: {line}")

    print("\n--- Possible Google job URLs ---")

    urls = re.findall(
        r'https://www\.google\.com/about/careers/applications/jobs/results/[A-Za-z0-9_-]+',
        response.text,
    )

    unique_urls = list(dict.fromkeys(urls))

    for url in unique_urls[:20]:
        print(url)

    print(f"\nUnique possible job URLs found: {len(unique_urls)}")


if __name__ == "__main__":
    main()