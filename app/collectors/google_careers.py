from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.collectors.base import JobCollector


BASE_URL = "https://www.google.com/about/careers/applications/"


class GoogleCareersCollector(JobCollector):
    """
    Collect job listings from Google Careers search results.
    """

    SEARCH_URL = urljoin(
        BASE_URL,
        "jobs/results/",
    )

    def __init__(
        self,
        query: str | None = None,
        location: str | None = None,
        page: int = 1,
    ) -> None:
        self.query = query
        self.location = location
        self.page = page

        self.session = requests.Session()

        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/153.0.0.0 Safari/537.36"
                )
            }
        )

    def _build_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "page": self.page,
        }

        if self.query:
            params["q"] = self.query

        if self.location:
            params["location"] = self.location

        return params

    def collect(self) -> list[dict[str, Any]]:
        response = self.session.get(
            self.SEARCH_URL,
            params=self._build_params(),
            timeout=30,
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        jobs: list[dict[str, Any]] = []

        # Google currently renders each search result as an <li>.
        # We locate cards by their title element rather than
        # relying on a single generated CSS class.
        for title_element in soup.find_all("h3"):
            title = title_element.get_text(
                " ",
                strip=True,
            )

            if not title:
                continue

            card = title_element.find_parent("li")

            if card is None:
                continue

            job = self._parse_job_card(
                card=card,
                title=title,
            )

            if job is not None:
                jobs.append(job)

        return jobs

    def _parse_job_card(
        self,
        card: Any,
        title: str,
    ) -> dict[str, Any] | None:
        # Company
        company = None

        company_icon = card.find(
            "i",
            string=lambda value: (
                value and value.strip() == "corporate_fare"
            ),
        )

        if company_icon is not None:
            company_span = company_icon.find_parent("span")

            if company_span is not None:
                spans = company_span.find_all(
                    "span",
                    recursive=True,
                )

                if spans:
                    company = spans[-1].get_text(
                        " ",
                        strip=True,
                    )

        # Fallback: Google cards currently contain
        # "Google | locations" in a <p>.
        if not company:
            company_paragraph = card.find(
                "p",
                class_="l103df",
            )

            if company_paragraph:
                text = company_paragraph.get_text(
                    " ",
                    strip=True,
                )

                if "|" in text:
                    company = text.split("|", 1)[0].strip()

        if not company:
            company = "Google"

        # Locations
        locations: list[str] = []

        location_icon = card.find(
            "i",
            string=lambda value: (
                value and value.strip() == "place"
            ),
        )

        if location_icon is not None:
            location_container = location_icon.find_parent("span")

            if location_container is not None:
                location_elements = location_container.find_all(
                    "span",
                    class_="r0wTof",
                )

                for element in location_elements:
                    value = element.get_text(
                        " ",
                        strip=True,
                    )

                    if value:
                        value = value.lstrip("; ").strip()

                        if value:
                            locations.append(value)

        # Experience
        experience = None

        experience_button = card.find(
            "button",
            attrs={
                "aria-label": lambda value: (
                    value
                    and "experience filters" in value.lower()
                )
            },
        )

        if experience_button is not None:
            experience = experience_button.get_text(
                " ",
                strip=True,
            )

        # Qualifications / description
        description_parts: list[str] = []

        for heading in card.find_all(
            ["h4", "h5"],
        ):
            heading_text = heading.get_text(
                " ",
                strip=True,
            )

            if heading_text.lower() in {
                "minimum qualifications",
                "preferred qualifications",
            }:
                parent = heading.parent

                if parent is not None:
                    text = parent.get_text(
                        "\n",
                        strip=True,
                    )

                    if text:
                        description_parts.append(text)

        description = "\n\n".join(
            dict.fromkeys(description_parts)
        )

        # URL
        link = card.find(
            "a",
            attrs={
                "aria-label": lambda value: (
                    value
                    and value.lower().startswith(
                        "learn more about "
                    )
                )
            },
        )

        if link is None:
            return None

        href = link.get("href")

        if not href:
            return None

        job_url = urljoin(
            BASE_URL,
            href,
        )

        return {
            "company": company,
            "title": title,
            "location": "; ".join(locations),
            "experience": experience,
            "url": job_url,
            "description": description,
            "source": "google_careers",
        }