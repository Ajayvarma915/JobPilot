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

    target = soup.find(
        "h3",
        string=re.compile(
            r"Software Engineer",
            re.IGNORECASE,
        ),
    )

    if target is None:
        print("Could not find a Software Engineer job.")
        return

    print("TITLE:")
    print(target.get_text(" ", strip=True))

    # Walk upward until we reach the LI containing the job.
    card = target.find_parent("li")

    if card is None:
        print("Could not find parent <li>.")
        return

    print("\n========== JOB CARD ATTRIBUTES ==========")
    print(card.attrs)

    print("\n========== LINKS ==========")

    links = card.find_all("a")

    for index, link in enumerate(links, start=1):
        print(f"\nLINK {index}")
        print("Text:", link.get_text(" ", strip=True))
        print("Href:", link.get("href"))
        print("Attrs:", link.attrs)

    print("\n========== DATA ATTRIBUTES ==========")

    for element in card.find_all(True):
        data_attrs = {
            key: value
            for key, value in element.attrs.items()
            if key.startswith("data-")
        }

        if data_attrs:
            print(element.name, data_attrs)

    print("\n========== JOB CARD TEXT ==========")

    print(card.get_text("\n", strip=True))

    print("\n========== JOB CARD HTML (first 15000 chars) ==========")

    print(card.prettify()[:15000])


if __name__ == "__main__":
    main()