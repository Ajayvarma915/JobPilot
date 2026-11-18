"""Retry with backoff for career-site requests.

A live sync reads hundreds of pages from sites we do not control. A single 429 or 503 should not
fail a whole company, so every collector session retries a few times with growing waits. Only
temporary failures are retried (rate limits and 5xx); a 404 or 403 still fails straight away.
"""
from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

RETRY_STATUSES = (429, 500, 502, 503, 504)


def with_retries(session: requests.Session, *, total: int = 3, backoff_factor: float = 0.8) -> requests.Session:
    """Mount a retrying adapter on the session (GET and POST list calls are safe to repeat)."""
    retry = Retry(
        total=total,
        connect=total,
        read=total,
        status=total,
        backoff_factor=backoff_factor,
        status_forcelist=RETRY_STATUSES,
        allowed_methods=frozenset({"GET", "POST"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
