"""On-demand check of whether a stored job is still on the employer's career site.

The check re-reads the job's own source (list only, no per-job detail requests) and looks for
the job's external id. It can answer three things:

- open:    the id is still listed, so the job's "last confirmed open" time is refreshed.
- closed:  the source answered normally, with a believable number of jobs, and the id is gone.
- unknown: anything else (no connector, network error, an empty or suspiciously small answer).
           An unknown result NEVER closes a job: a flaky site must not wipe your jobs.
"""
from __future__ import annotations

import copy
from typing import Any

OPEN = "open"
CLOSED = "closed"
UNKNOWN = "unknown"

# A source answering with fewer than this share of the jobs we hold active looks partial.
MIN_SHARE_OF_STORED = 0.5


def list_only(company: dict[str, Any]) -> dict[str, Any]:
    """Copy of a registry entry whose connector skips per-job detail requests."""
    clone = copy.deepcopy(company)
    settings = (clone.get("integration") or {}).get("settings")
    if isinstance(settings, dict):
        settings["fetch_details"] = False
    return clone


def decide(
    *,
    external_id: str | None,
    fetched_ids: set[str],
    stored_active_count: int,
) -> tuple[str, str]:
    """Return (status, reason) from what the source listed."""
    if not external_id:
        return UNKNOWN, "This job has no source id, so it cannot be looked up."
    if not fetched_ids:
        return UNKNOWN, "The source returned no jobs at all, so nothing can be concluded."
    if external_id in fetched_ids:
        return OPEN, "The job is still listed on the employer's career site."
    if stored_active_count and len(fetched_ids) < stored_active_count * MIN_SHARE_OF_STORED:
        return UNKNOWN, (f"The source listed only {len(fetched_ids)} jobs against {stored_active_count} stored, "
                         "which looks like a partial answer, so the job was not closed.")
    return CLOSED, "The source answered normally and this job is no longer listed."


def classify_google_page(status_code: int, text: str) -> tuple[str, str]:
    """Decide from one Google Careers job page whether the job is still posted.

    Google answers a taken-down job with a normal page that says "Job not found / This job may have
    been taken down" (seen live), and an open job's page lists its Responsibilities. Anything else,
    including a failed request, is unknown and changes nothing.
    """
    if status_code in (404, 410):
        return CLOSED, "Google's career site no longer has this page."
    if status_code != 200:
        return UNKNOWN, f"Google's career site answered with status {status_code}, so nothing can be concluded."
    lowered = text.lower()
    if "job not found" in lowered and "taken down" in lowered:
        return CLOSED, "Google's career site says this job was taken down."
    if "responsibilities" in lowered:
        return OPEN, "The job is still posted on Google's career site."
    return UNKNOWN, "The page did not clearly show the job, so it was left unchanged."


_CLOSED_PHRASES = (
    "no longer accepting applications", "no longer available", "no longer open", "position has been filled", "has been filled",
    "job has expired", "posting has expired", "this position is closed", "this job is closed", "this job has been closed",
    "applications are closed", "job not found", "page not found", "this opportunity is no longer", "role has been closed",
    "this position has been closed",
)


def classify_job_page(status_code: int, text: str, title: str) -> tuple[str, str]:
    """Decide from a job's OWN page whether it is still posted (used when no job list can be read).

    Closed only on a clear signal (the page is gone, or it says the job is closed or filled). Open only when
    the page still shows the job's title. Anything else is unknown and changes nothing.
    """
    if status_code in (404, 410):
        return CLOSED, "The employer's page for this job no longer exists."
    if status_code != 200:
        return UNKNOWN, f"The job's page answered with status {status_code}, so nothing can be concluded."
    lowered = text.lower()
    if any(phrase in lowered for phrase in _CLOSED_PHRASES):
        return CLOSED, "The job's own page says it is closed or no longer available."
    clean_title = " ".join(title.lower().split())
    if clean_title and clean_title in " ".join(lowered.split()):
        return OPEN, "The job's own page still shows this posting."
    return UNKNOWN, "The page did not clearly show the job, so it was left unchanged."
