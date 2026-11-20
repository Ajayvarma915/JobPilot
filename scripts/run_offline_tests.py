"""Run every offline test in one go, safely.

    python -m scripts.run_offline_tests            # all offline tests
    python -m scripts.run_offline_tests -k email   # only tests whose name contains "email"

Each Python test runs as `python -m scripts.<name>` against a TEMPORARY COPY of your database
(JOBPILOT_DATABASE_PATH points at the copy), so nothing here can change your real data. Node
tests for the browser extension run too when Node is installed.

Skipped on purpose, because they need something this script will not assume: live network access
(real career sites), a running Ollama, or your personal resume under data/master_resume. Run those
by hand when you want them; they are listed in the summary so a skip is never mistaken for a pass.
The exit code is non-zero if any test fails.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

NEEDS_LIVE_SERVICES = {
    "test_environment": "checks the local machine setup",
    "test_google_careers": "calls Google Careers live",
    # These four also fetch the real Google Careers site (they failed on a slow connection, so they are not offline).
    "test_google_collector": "calls Google Careers live",
    "test_google_job_details": "calls Google Careers live",
    "test_google_pagination": "calls Google Careers live",
    "test_google_pagination_details": "calls Google Careers live",
    "test_greenhouse": "calls Greenhouse live",
    "test_greenhouse_connection": "calls Greenhouse live",
    "test_requests": "makes a live HTTP request",
    "test_ollama": "needs a running Ollama",
    "test_ollama_jd_analysis": "needs a running Ollama",
    "test_resume_evidence_selector": "needs your personal resume in data/master_resume",
    "test_resume_evidence_store": "needs your personal resume in data/master_resume",
    "test_resume_parser": "needs your personal resume in data/master_resume",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all offline tests against a temporary database copy.")
    parser.add_argument("-k", dest="keyword", default="", help="Only run tests whose name contains this text.")
    parser.add_argument("--timeout", type=int, default=300, help="Seconds allowed per test (default 300).")
    args = parser.parse_args()

    names = sorted(p.stem for p in (PROJECT_ROOT / "scripts").glob("test_*.py") if args.keyword in p.stem)
    node_tests = [p for p in [PROJECT_ROOT / "scripts" / "test_extension_field_matcher.mjs",
                              PROJECT_ROOT / "scripts_test_extension_submission_confirmation.mjs"]
                  if p.is_file() and args.keyword in p.stem]

    results: list[tuple[str, str, float, str]] = []
    with tempfile.TemporaryDirectory(prefix="jobpilot_tests_") as temp:
        database = Path(temp) / "jobpilot.db"
        real = PROJECT_ROOT / "jobpilot.db"
        if real.is_file():
            shutil.copyfile(real, database)
        env = {**os.environ, "JOBPILOT_DATABASE_PATH": str(database), "PYTHONIOENCODING": "utf-8", "PYTHONWARNINGS": "ignore"}
        env.pop("JOBPILOT_API_TOKEN", None)

        for name in names:
            if name in NEEDS_LIVE_SERVICES:
                results.append((name, "SKIP", 0.0, NEEDS_LIVE_SERVICES[name]))
                continue
            started = time.monotonic()
            try:
                completed = subprocess.run([sys.executable, "-m", f"scripts.{name}"], cwd=PROJECT_ROOT, env=env,
                                           capture_output=True, text=True, timeout=args.timeout, encoding="utf-8", errors="replace")
                ok, tail = completed.returncode == 0, (completed.stdout + completed.stderr).strip().splitlines()[-3:]
            except subprocess.TimeoutExpired:
                ok, tail = False, [f"timed out after {args.timeout}s"]
            results.append((name, "PASS" if ok else "FAIL", time.monotonic() - started, "" if ok else " | ".join(tail)))
            print(f"{results[-1][1]:5} {name} ({results[-1][2]:.1f}s)", flush=True)

        node = shutil.which("node")
        for path in node_tests:
            if not node:
                results.append((path.name, "SKIP", 0.0, "Node.js is not installed"))
                continue
            started = time.monotonic()
            completed = subprocess.run([node, str(path.relative_to(PROJECT_ROOT))], cwd=PROJECT_ROOT, capture_output=True,
                                       text=True, timeout=args.timeout, encoding="utf-8", errors="replace")
            ok = completed.returncode == 0
            results.append((path.name, "PASS" if ok else "FAIL", time.monotonic() - started,
                            "" if ok else " | ".join((completed.stdout + completed.stderr).strip().splitlines()[-3:])))
            print(f"{results[-1][1]:5} {path.name} ({results[-1][2]:.1f}s)", flush=True)

    passed = sum(1 for r in results if r[1] == "PASS")
    failed = [r for r in results if r[1] == "FAIL"]
    skipped = [r for r in results if r[1] == "SKIP"]
    print(f"\n{passed} passed, {len(failed)} failed, {len(skipped)} skipped (skipped tests were NOT run)")
    for name, _, _, reason in skipped:
        print(f"  skipped {name}: {reason}")
    for name, _, _, reason in failed:
        print(f"  FAILED  {name}: {reason}")
    print("Your real database was not touched (tests ran on a temporary copy).")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
