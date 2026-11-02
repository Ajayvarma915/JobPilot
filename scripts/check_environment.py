"""Check local JobPilot prerequisites without printing secret values."""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple


ROOT = Path(__file__).resolve().parents[1]


class Check(NamedTuple):
    label: str
    ok: bool
    detail: str
    required: bool = True


def command_version(command: str, args: list[str]) -> str | None:
    executable = shutil.which(command)
    if not executable:
        return None
    try:
        completed = subprocess.run(
            [executable, *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "found, but version check failed"
    output = (completed.stdout or completed.stderr).strip().splitlines()
    return output[0] if output else "found, version unavailable"


def module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def main() -> int:
    checks: list[Check] = []
    checks.append(
        Check(
            "Python",
            sys.version_info >= (3, 11),
            sys.version.split()[0],
        )
    )

    dependencies = {
        "FastAPI": "fastapi",
        "Uvicorn": "uvicorn",
        "Pydantic": "pydantic",
        "SQLAlchemy": "sqlalchemy",
        "Requests": "requests",
        "BeautifulSoup": "bs4",
        "python-docx": "docx",
        "ReportLab": "reportlab",
        "pypdf": "pypdf",
        "Google API client": "googleapiclient",
        "Google OAuth library": "google_auth_oauthlib",
    }
    for label, module in dependencies.items():
        checks.append(
            Check(label, module_available(module), "installed" if module_available(module) else "not installed")
        )

    checks.append(
        Check(
            "Job-source configuration",
            (ROOT / "data" / "job_sources.json").is_file(),
            "data/job_sources.json present" if (ROOT / "data" / "job_sources.json").is_file() else "missing",
        )
    )
    checks.append(
        Check(
            "Frontend package manifest",
            (ROOT / "frontend" / "package.json").is_file()
            and (ROOT / "frontend" / "package-lock.json").is_file(),
            "package.json and package-lock.json present"
            if (ROOT / "frontend" / "package.json").is_file()
            and (ROOT / "frontend" / "package-lock.json").is_file()
            else "frontend manifest or lockfile missing",
        )
    )

    node_version = command_version("node", ["--version"])
    npm_version = command_version("npm", ["--version"])
    checks.append(Check("Node.js", node_version is not None, node_version or "not found"))
    checks.append(Check("npm", npm_version is not None, npm_version or "not found"))

    oauth_file = ROOT / "credentials" / "gmail_oauth_client.json"
    token_file = ROOT / "tokens" / "gmail_token.json"
    db_file = ROOT / "jobpilot.db"
    checks.extend(
        [
            Check(
                "Google OAuth client file",
                oauth_file.is_file(),
                "present" if oauth_file.is_file() else "not present (required only to connect Gmail)",
                required=False,
            ),
            Check(
                "Gmail token file",
                token_file.is_file(),
                "present" if token_file.is_file() else "not present (created after Gmail authorization)",
                required=False,
            ),
            Check(
                "SQLite database",
                db_file.is_file(),
                "jobpilot.db present" if db_file.is_file() else "not present (initialize for a new setup)",
                required=False,
            ),
        ]
    )

    print("JobPilot environment preflight")
    print("=" * 72)
    for item in checks:
        status = "PASS" if item.ok else ("FAIL" if item.required else "INFO")
        print(f"[{status:4}] {item.label:28} {item.detail}")

    failures = [item for item in checks if item.required and not item.ok]
    print("=" * 72)
    if failures:
        print(f"{len(failures)} required check(s) failed. Install missing dependencies or tools.")
        print("For Python packages, run: pip install -r requirements.txt")
        return 1

    print("Required local environment checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
