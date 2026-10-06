from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.collectors.base import JobCollector
from app.collectors.google_job_details import (
    GoogleJobDetailFetcher,
)


BASE_URL = (
    "https://www.google.com/about/careers/applications/"
)

SEARCH_URL = urljoin(
    BASE_URL,
    "jobs/results/",
)


class GoogleCareersCollector(JobCollector):
    """Collect jobs from Google Careers search results."""

    def __init__(
        self,
        query: str | None = None,
        location: str | None = None,
        page: int = 1,
        fetch_details: bool = False,
        max_pages: int = 1,
    ) -> None:
        self.query = query
        self.location = location
        self.page = page
        self.fetch_details = fetch_details
        self.max_pages = max(1, max_pages)

        self.session = requests.Session()

        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/153.0.0.0 "
                    "Safari/537.36"
                )
            }
        )

        self.detail_fetcher = (
            GoogleJobDetailFetcher()
        )

    def _build_params(
        self,
        page: int,
    ) -> dict[str, Any]:
        """Build Google Careers search parameters."""

        params: dict[str, Any] = {
            "page": page,
        }

        if self.query:
            params["q"] = self.query

        if self.location:
            params["location"] = self.location

        return params

    def collect(
        self,
    ) -> list[dict[str, Any]]:
        """
        Collect jobs from one or more Google Careers
        search-result pages.

        max_pages controls the number of search pages.
        """

        jobs: list[
            dict[str, Any]
        ] = []

        seen_ids: set[str] = set()
        seen_urls: set[str] = set()

        for page_number in range(
            self.page,
            self.page + self.max_pages,
        ):
            print(
                f"Collecting Google Careers "
                f"page {page_number}..."
            )

            page_jobs = (
                self._collect_page(
                    page_number
                )
            )

            print(
                f"Page {page_number}: "
                f"{len(page_jobs)} jobs found."
            )

            if not page_jobs:
                print(
                    "No jobs returned. "
                    "Stopping pagination."
                )
                break

            new_jobs = 0

            for job in page_jobs:
                external_id = job.get(
                    "external_id"
                )

                url = job.get("url")

                # Prefer external_id as the primary
                # identity, with URL as a fallback.
                if external_id:
                    if external_id in seen_ids:
                        continue

                    seen_ids.add(external_id)

                elif url:
                    if url in seen_urls:
                        continue

                    seen_urls.add(url)

                jobs.append(job)
                new_jobs += 1

            print(
                f"Page {page_number}: "
                f"{new_jobs} new unique jobs."
            )

            # Small delay between search pages.
            if page_number < (
                self.page
                + self.max_pages
                - 1
            ):
                time.sleep(0.5)

        if self.fetch_details:
            jobs = self._enrich_with_details(
                jobs
            )

        return jobs

    def _collect_page(
        self,
        page: int,
    ) -> list[dict[str, Any]]:
        """Collect jobs from one search-result page."""

        response = self.session.get(
            SEARCH_URL,
            params=self._build_params(page),
            timeout=30,
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        jobs: list[
            dict[str, Any]
        ] = []

        for title_element in soup.find_all("h3"):
            title = title_element.get_text(
                " ",
                strip=True,
            )

            if not title:
                continue

            card = title_element.find_parent(
                "li"
            )

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
        """Parse one Google Careers search result card."""

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

        canonical_url = (
            self._canonicalize_url(href)
        )

        external_id = (
            self._extract_external_id(
                canonical_url
            )
        )

        # ---------------------------------------------------------
        # Company
        # ---------------------------------------------------------

        company = "Google"

        company_paragraph = card.find(
            "p",
            class_="l103df",
        )

        if company_paragraph is not None:
            paragraph_text = (
                company_paragraph.get_text(
                    " ",
                    strip=True,
                )
            )

            if "|" in paragraph_text:
                company = (
                    paragraph_text
                    .split("|", 1)[0]
                    .strip()
                )

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
                location_icon.find_parent(
                    "span"
                )
            )

            if location_container is not None:
                location_elements = (
                    location_container.find_all(
                        "span",
                        class_="r0wTof",
                    )
                )

                for element in (
                    location_elements
                ):
                    value = element.get_text(
                        " ",
                        strip=True,
                    )

                    value = value.lstrip(
                        "; "
                    ).strip()

                    if value:
                        locations.append(
                            value
                        )

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
        # Search-card description
        # ---------------------------------------------------------

        description = (
            self._extract_description(card)
        )

        return {
            "external_id": external_id,
            "company": company,
            "title": title,
            "location": locations,
            "url": canonical_url,
            "description": description,
            "experience_level": (
                experience_level
            ),
            "source": "google_careers",
        }

    @staticmethod
    def _canonicalize_url(
        href: str,
    ) -> str:
        """
        Convert a relative Google Careers URL
        into a canonical URL.

        Search parameters are removed.
        """

        absolute_url = urljoin(
            BASE_URL,
            href,
        )

        parsed = urlparse(
            absolute_url
        )

        return parsed._replace(
            query="",
            fragment="",
        ).geturl()

    @staticmethod
    def _extract_external_id(
        job_url: str,
    ) -> str | None:
        """
        Extract the numeric Google job ID.

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
    def _extract_description(
        card: Any,
    ) -> str:
        """
        Extract useful text from a Google search card.

        This is only a fallback/preview description.
        The detail-page fetcher provides the full JD.
        """

        sections: list[str] = []

        # ---------------------------------------------------------
        # Experience explanation
        # ---------------------------------------------------------

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

        # ---------------------------------------------------------
        # Qualification sections
        # ---------------------------------------------------------

        for heading in card.find_all(
            ["h4", "h5"],
        ):
            heading_text = (
                heading.get_text(
                    " ",
                    strip=True,
                )
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
                for li in parent.find_all(
                    "li"
                ):
                    text = li.get_text(
                        " ",
                        strip=True,
                    )

                    if text:
                        section_parts.append(
                            text
                        )

            sections.append(
                "\n".join(
                    section_parts
                )
            )

        unique_sections = list(
            dict.fromkeys(sections)
        )

        return "\n\n".join(
            unique_sections
        )

    def _enrich_with_details(
        self,
        jobs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Fetch the individual Google Careers
        detail page for every collected job.
        """

        enriched_jobs: list[
            dict[str, Any]
        ] = []

        for index, job in enumerate(
            jobs,
            start=1,
        ):
            print(
                f"Fetching details "
                f"{index}/{len(jobs)}: "
                f"{job['title']}"
            )

            try:
                details = (
                    self.detail_fetcher.fetch(
                        url=job["url"],
                        fallback_title=job[
                            "title"
                        ],
                    )
                )

                if details.get("title"):
                    job["title"] = (
                        details["title"]
                    )

                if details.get(
                    "description"
                ):
                    job["description"] = (
                        details["description"]
                    )

                job["detail_sections"] = (
                    details.get(
                        "sections",
                        {},
                    )
                )

                enriched_jobs.append(job)

            except requests.RequestException as exc:
                print(
                    "WARNING: Could not fetch "
                    f"details for {job['url']}"
                )

                print(
                    f"Reason: {exc}"
                )

                # Keep the search-card data.
                enriched_jobs.append(job)

            except Exception as exc:
                print(
                    "WARNING: Unexpected error "
                    f"while fetching {job['url']}"
                )

                print(
                    f"Reason: {exc}"
                )

                # Keep the search-card data.
                enriched_jobs.append(job)

            if index < len(jobs):
                time.sleep(0.5)

        return enriched_jobs