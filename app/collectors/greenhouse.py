from typing import Any

import requests

from app.collectors.base import JobCollector


class GreenhouseCollector(JobCollector):

    def __init__(self, board_token: str, company_name: str):
        self.board_token = board_token
        self.company_name = company_name

    def collect(self) -> list[dict[str, Any]]:
        url = (
            f"https://boards-api.greenhouse.io/v1/boards/"
            f"{self.board_token}/jobs"
        )

        response = requests.get(
            url,
            params={"content": "true"},
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()

        jobs = []

        for job in data.get("jobs", []):
            jobs.append(
                {
                    "company": self.company_name,
                    "title": job.get("title"),
                    "location": (
                        job.get("location", {}).get("name")
                        if job.get("location")
                        else None
                    ),
                    "url": job.get("absolute_url"),
                    "description": job.get("content", ""),
                    "source": "greenhouse",
                }
            )

        return jobs