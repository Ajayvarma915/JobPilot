"""Tests for collector retry/backoff using a local fake server (no internet)."""
from __future__ import annotations

import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

from app.collectors.http_retry import with_retries


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def serve(statuses: list[int]):
    hits = {"n": 0}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            code = statuses[min(hits["n"], len(statuses) - 1)]
            hits["n"] += 1
            self.send_response(code)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, hits


def test_temporary_failures_are_retried() -> None:
    server, hits = serve([503, 429, 200])
    try:
        session = with_retries(requests.Session(), backoff_factor=0.01)
        response = session.get(f"http://127.0.0.1:{server.server_port}/")
        check(response.status_code == 200 and hits["n"] == 3, f"two temporary failures, then success: hits={hits['n']}")
    finally:
        server.shutdown()


def test_permanent_failures_are_not_retried() -> None:
    server, hits = serve([404])
    try:
        session = with_retries(requests.Session(), backoff_factor=0.01)
        response = session.get(f"http://127.0.0.1:{server.server_port}/")
        check(response.status_code == 404 and hits["n"] == 1, f"a 404 is final: hits={hits['n']}")
    finally:
        server.shutdown()


def test_gives_up_after_the_limit() -> None:
    server, hits = serve([503])
    try:
        session = with_retries(requests.Session(), total=2, backoff_factor=0.01)
        response = session.get(f"http://127.0.0.1:{server.server_port}/")
        check(response.status_code == 503 and hits["n"] == 3, f"1 try + 2 retries then the 503 is returned: hits={hits['n']}")
    finally:
        server.shutdown()


class _FakeResponse:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        if self.body is None:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self.body


class _FakeSession:
    def __init__(self, bodies):
        self.bodies = list(bodies)
        self.calls = 0

    def post(self, *args, **kwargs):
        self.calls += 1
        return _FakeResponse(self.bodies.pop(0))

    def get(self, *args, **kwargs):
        raise AssertionError("no detail requests expected")


def test_workday_retries_an_unreadable_body() -> None:
    import time
    from app.collectors.workday import WorkdayCollector

    original_sleep = time.sleep
    time.sleep = lambda _s: None
    try:
        collector = WorkdayCollector(tenant="t", site="s", company_name="Acme", host="acme.example", fetch_details=False)
        collector.session = _FakeSession([None, None, {"jobPostings": [], "total": 0}])
        check(collector.collect() == [] and collector.session.calls == 3, "an empty body twice, then a good page")
        collector.session = _FakeSession([None, None, None])
        try:
            collector.collect()
            raise AssertionError("three unreadable bodies must fail loudly")
        except ValueError as exc:
            check("unreadable body" in str(exc), str(exc))
    finally:
        time.sleep = original_sleep


TESTS = [
    ("Temporary failures are retried", test_temporary_failures_are_retried),
    ("A 404 is not retried", test_permanent_failures_are_not_retried),
    ("Retries stop at the limit", test_gives_up_after_the_limit),
    ("Workday retries an unreadable list page", test_workday_retries_an_unreadable_body),
]


def main() -> int:
    failed = 0
    for name, test in TESTS:
        try:
            test()
            print(f"PASS - {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL - {name}: {type(exc).__name__}: {exc}")
    print(f"\nUnit tests: {len(TESTS) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
