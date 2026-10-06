from __future__ import annotations

import re
from typing import Any

import requests
from bs4 import BeautifulSoup


class GoogleJobDetailFetcher:
    """Fetch and parse individual Google Careers job pages."""

    TARGET_SECTIONS = {
        "about the job",
        "minimum qualifications",
        "preferred qualifications",
        "responsibilities",
    }

    HEADINGS = [
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    ]

    FOOTER_MARKERS = [
        "information collected and processed as part of your google careers profile",
        "google is proud to be an equal opportunity",
        "if you have a need that requires accommodation",
        "to all recruitment agencies",
        "equity is granted exclusively and discretionarily",
    ]

    def __init__(self) -> None:
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

    def fetch(
        self,
        url: str,
        fallback_title: str | None = None,
    ) -> dict[str, Any]:
        """Fetch and parse one Google Careers job page."""

        response = self.session.get(
            url,
            timeout=30,
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        title = self._extract_title(
            soup,
            fallback_title,
        )

        sections = self._extract_sections(
            soup
        )

        description = self._combine_sections(
            sections
        )

        return {
            "title": title,
            "description": description,
            "sections": sections,
            "url": url,
        }

    @staticmethod
    def _extract_title(
        soup: BeautifulSoup,
        fallback_title: str | None,
    ) -> str | None:
        """
        Extract the real job title.

        Google may expose a generic 'job details' heading
        on the detail page, so a known title from the
        search result is used as a reliable fallback.
        """

        heading = soup.find("h1")

        if heading is not None:
            title = heading.get_text(
                " ",
                strip=True,
            )

            normalized = title.lower()

            if title and normalized not in {
                "job details",
                "job detail",
            }:
                return title

        return fallback_title

    def _extract_sections(
        self,
        soup: BeautifulSoup,
    ) -> dict[str, str]:
        """
        Extract the important job-detail sections
        using semantic heading text.
        """

        sections: dict[str, str] = {}

        for heading in soup.find_all(
            self.HEADINGS
        ):
            heading_text = self._normalize_heading(
                heading.get_text(
                    " ",
                    strip=True,
                )
            )

            if heading_text not in self.TARGET_SECTIONS:
                continue

            content = self._extract_heading_content(
                heading
            )

            if content:
                sections[heading_text] = (
                    content
                )

        return sections

    def _extract_heading_content(
        self,
        heading: Any,
    ) -> str:
        """
        Collect paragraphs and list items after a heading
        until another major heading is reached.
        """

        parts: list[str] = []

        for element in heading.next_elements:

            if (
                getattr(element, "name", None)
                in self.HEADINGS
            ):
                break

            tag_name = getattr(
                element,
                "name",
                None,
            )

            if tag_name not in {
                "p",
                "li",
            }:
                continue

            text = element.get_text(
                " ",
                strip=True,
            )

            if not text:
                continue

            if text not in parts:
                parts.append(text)

        return "\n".join(parts)

    @staticmethod
    def _normalize_heading(
        text: str,
    ) -> str:
        text = text.strip().lower()

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        text = text.rstrip(":")

        return text.strip()

    @classmethod
    def _remove_footer_boilerplate(
        cls,
        text: str,
    ) -> str:
        """
        Remove Google's standard legal/recruitment
        footer content from the AI-facing JD.
        """

        lower_text = text.lower()

        cut_positions = []

        for marker in cls.FOOTER_MARKERS:
            position = lower_text.find(marker)

            if position != -1:
                cut_positions.append(position)

        if cut_positions:
            cutoff = min(cut_positions)
            text = text[:cutoff].rstrip()

        return text

    @classmethod
    def _combine_sections(
        cls,
        sections: dict[str, str],
    ) -> str:
        """
        Produce one clean, AI-friendly job description.
        """

        ordered_sections = [
            "about the job",
            "minimum qualifications",
            "preferred qualifications",
            "responsibilities",
        ]

        parts: list[str] = []

        for section_name in ordered_sections:
            content = sections.get(
                section_name
            )

            if not content:
                continue

            parts.append(
                f"{section_name.title()}\n"
                f"{content}"
            )

        description = "\n\n".join(parts)

        return cls._remove_footer_boilerplate(
            description
        )