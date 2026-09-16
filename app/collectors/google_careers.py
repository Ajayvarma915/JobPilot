from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.collectors.base import JobCollector


BASE_URL = "https://www.google.com/about/careers/applications/"
SEARCH_URL = urljoin(BASE_URL, "jobs/results/")


class GoogleCareersCollector(JobCollector):
    """Collect jobs from Google Careers search results."""

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
            SEARCH_URL,
            params=self._build_params(),
            timeout=30,
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        jobs: list[dict[str, Any]] = []

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
                card,
                title,
            )

            if job is not None:
                jobs.append(job)

        return jobs

    def _parse_job_card(
        self,
        card: Any,
        title: str,
    ) -> dict[str, Any] | None:

        # ---------------------------------------------------------
        # Job URL + external ID
        # ---------------------------------------------------------

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

        canonical_url = self._canonicalize_url(href)

        external_id = self._extract_external_id(
            canonical_url
        )

        # ---------------------------------------------------------
        # Company
        # ---------------------------------------------------------

        company = "Google"

        # Google's current search cards contain a company
        # paragraph such as:
        #
        # Google | Mountain View, CA, USA
        #
        company_paragraph = card.find(
            "p",
            class_="l103df",
        )

        if company_paragraph is not None:
            paragraph_text = company_paragraph.get_text(
                " ",
                strip=True,
            )

            if "|" in paragraph_text:
                company = paragraph_text.split(
                    "|",
                    1,
                )[0].strip()

        # ---------------------------------------------------------
        # Locations
        # ---------------------------------------------------------

        locations: list[str] = []

        location_icon = card.find(
            "i",
            string=lambda value: (
                value
                and value.strip() == "place"
            ),
        )

        if location_icon is not None:

            location_container = (
                location_icon.find_parent("span")
            )

            if location_container is not None:

                location_elements = (
                    location_container.find_all(
                        "span",
                        class_="r0wTof",
                    )
                )

                for element in location_elements:

                    value = element.get_text(
                        " ",
                        strip=True,
                    )

                    value = value.lstrip("; ").strip()

                    if value:
                        locations.append(value)

        # Remove duplicate locations while preserving order.
        locations = list(
            dict.fromkeys(locations)
        )

        # ---------------------------------------------------------
        # Experience level
        # ---------------------------------------------------------

        experience_level = None

        experience_button = card.find(
            "button",
            attrs={
                "aria-label": lambda value: (
                    value
                    and "experience filters"
                    in value.lower()
                )
            },
        )

        if experience_button is not None:

            # Do NOT use button.get_text() because it also
            # contains Google's material icon text such as
            # "bar_chart".
            experience_span = (
                experience_button.find(
                    "span",
                    class_="wVSTAb",
                )
            )

            if experience_span is not None:
                experience_level = (
                    experience_span.get_text(
                        " ",
                        strip=True,
                    )
                )

        # ---------------------------------------------------------
        # Description
        # ---------------------------------------------------------

        description = self._extract_description(card)

        return {
            "external_id": external_id,
            "company": company,
            "title": title,
            "location": locations,
            "url": canonical_url,
            "description": description,
            "experience_level": experience_level,
            "source": "google_careers",
        }

    @staticmethod
    def _canonicalize_url(href: str) -> str:
        """
        Convert Google's relative job URL into a canonical URL.

        Search parameters such as ?page=1&q=... are removed.
        """

        absolute_url = urljoin(
            BASE_URL,
            href,
        )

        parsed = urlparse(absolute_url)

        return parsed._replace(
            query="",
            fragment="",
        ).geturl()

    @staticmethod
    def _extract_external_id(
        job_url: str,
    ) -> str | None:
        """
        Extract the numeric Google job ID from the URL.

        Example:
        /jobs/results/100397...-software-engineer
        """

        match = re.search(
            r"/jobs/results/(\d+)-",
            job_url,
        )

        if match is None:
            return None

        return match.group(1)

    @staticmethod
    def _extract_description(card: Any) -> str:
        """
        Extract the useful textual content from the job card.

        We currently include:
        - experience description
        - minimum qualifications
        - preferred qualifications

        We deliberately avoid buttons such as Share / Email.
        """

        sections: list[str] = []

        # Experience explanation
        experience_tooltip = card.find(
            "div",
            role="tooltip",
        )

        if experience_tooltip is not None:
            text = experience_tooltip.get_text(
                " ",
                strip=True,
            )

            if text:
                sections.append(text)

        # Qualification sections
        for heading in card.find_all(
            ["h4", "h5"],
        ):
            heading_text = heading.get_text(
                " ",
                strip=True,
            )

            normalized_heading = (
                heading_text.lower()
            )

            if normalized_heading not in {
                "minimum qualifications",
                "preferred qualifications",
            }:
                continue

            section_parts = [
                heading_text
            ]

            parent = heading.parent

            if parent is not None:
                for li in parent.find_all("li"):
                    text = li.get_text(
                        " ",
                        strip=True,
                    )

                    if text:
                        section_parts.append(
                            text
                        )

            sections.append(
                "\n".join(section_parts)
            )

        # Remove exact duplicate sections while
        # preserving their original order.
        unique_sections = list(
            dict.fromkeys(sections)
        )

        return "\n\n".join(unique_sections)