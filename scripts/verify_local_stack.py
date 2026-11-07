from __future__ import annotations

"""Read-only local JobPilot integration preflight.

Checks the running FastAPI service, application tracker, Gmail read-only status,
email review queues, optional Ollama status, the built Vite bundle, and the
Chrome extension package. It never triggers OAuth, Gmail sync, application
status changes, or any other write operation.
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin


@dataclass
class Check:
    name: str
    status: str  # PASS, WARN, FAIL
    detail: str
    critical: bool = False


def get_json(base_url: str, path: str, timeout: float) -> tuple[int, Any]:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "JobPilot-Local-Preflight/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(2_000_000)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"{path} returned invalid JSON") from exc
            return response.status, payload
    except urllib.error.HTTPError as exc:
        body = exc.read(500).decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {path}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot reach {base_url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError(f"Timed out calling {path}") from exc


def _check_response_shape(payload: Any, required: tuple[str, ...]) -> bool:
    return isinstance(payload, dict) and all(key in payload for key in required)


def check_static_files(root: Path, api_base: str) -> list[Check]:
    results: list[Check] = []

    # Verify the production frontend bundle exists and all local assets resolve.
    index_path = root / "frontend" / "dist" / "index.html"
    if not index_path.is_file():
        results.append(Check("Frontend production build", "WARN", "frontend/dist/index.html not found; run npm run build."))
    else:
        html = index_path.read_text(encoding="utf-8", errors="replace")
        refs = re.findall(r'''(?:src|href)=["']([^"']+\.(?:js|css))(?:\?[^"']*)?["']''', html)
        missing = [ref for ref in refs if not (index_path.parent / ref.lstrip("/")).is_file()]
        if refs and not missing:
            results.append(Check("Frontend production build", "PASS", f"index.html and {len(refs)} bundled assets found."))
        elif not refs:
            results.append(Check("Frontend production build", "WARN", "index.html exists but no JS/CSS bundle references were detected."))
        else:
            results.append(Check("Frontend production build", "FAIL", f"Missing built assets: {', '.join(missing)}", critical=True))

    extension_dir = root / "browser_extension" / "jobpilot-form-assistant"
    manifest_path = extension_dir / "manifest.json"
    popup_path = extension_dir / "popup.js"
    popup_html_path = extension_dir / "popup.html"
    if not all(path.is_file() for path in (manifest_path, popup_path, popup_html_path)):
        results.append(Check("Chrome extension files", "FAIL", "Expected manifest.json, popup.js and popup.html under browser_extension/jobpilot-form-assistant.", critical=True))
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            permissions = manifest.get("host_permissions", [])
            popup_js = popup_path.read_text(encoding="utf-8", errors="replace")
            expected_origin = api_base.rstrip("/")
            popup_match = re.search(r'const\s+API_BASE\s*=\s*["\']([^"\']+)', popup_js)
            popup_origin = popup_match.group(1).rstrip("/") if popup_match else None
            host_allowed = any(expected_origin in item for item in permissions if isinstance(item, str))
            if manifest.get("manifest_version") == 3 and popup_origin == expected_origin and host_allowed:
                results.append(Check("Chrome extension configuration", "PASS", f"Manifest v3; popup and host permissions target {expected_origin}."))
            else:
                detail = f"manifest_version={manifest.get('manifest_version')}, popup API={popup_origin}, host permission match={host_allowed}."
                results.append(Check("Chrome extension configuration", "WARN", detail + " Check API_BASE/host_permissions if using a non-default API URL."))
        except (OSError, json.JSONDecodeError) as exc:
            results.append(Check("Chrome extension configuration", "FAIL", f"Could not read extension metadata: {exc}", critical=True))

    return results


def run_checks(base_url: str, root: Path, timeout: float = 4.0) -> list[Check]:
    checks: list[Check] = []

    def call(name: str, path: str, required: tuple[str, ...] = ()) -> Any | None:
        try:
            status, payload = get_json(base_url, path, timeout)
            if status != 200 or (required and not _check_response_shape(payload, required)):
                checks.append(Check(name, "FAIL", f"Unexpected response from {path} (HTTP {status}).", critical=True))
                return None
            return payload
        except Exception as exc:  # Continue to collect independent diagnostics.
            checks.append(Check(name, "FAIL", str(exc), critical=True))
            return None

    health = call("Backend + primary database", "/api/health", ("status", "database", "jobs_available", "companies_available"))
    if health is not None:
        good = health.get("status") == "ok" and health.get("database") == "connected"
        checks.append(Check(
            "Backend + primary database",
            "PASS" if good else "FAIL",
            f"status={health.get('status')}; database={health.get('database')}; jobs={health.get('jobs_available')}; companies={health.get('companies_available')}",
            critical=not good,
        ))

    dashboard = call("Job discovery API", "/api/dashboard/stats", ("total_jobs", "active_jobs", "total_companies"))
    if dashboard is not None:
        checks.append(Check("Job discovery API", "PASS", f"{dashboard.get('active_jobs')} active / {dashboard.get('total_jobs')} total jobs across {dashboard.get('total_companies')} companies."))

    app_stats = call("Application tracker API", "/api/applications/stats", ("total", "needs_action", "by_status"))
    app_list = call("Application list API", "/api/applications?limit=1", ("items", "total", "limit", "offset"))
    if app_stats is not None and app_list is not None:
        checks.append(Check("Application tracker API", "PASS", f"{app_stats.get('total')} tracked applications; list endpoint responds."))

    email_status = call("Gmail status API", "/api/email/status", ("provider", "oauth_configured", "connected", "requested_scope", "stores_full_email_body"))
    if email_status is not None:
        configured = bool(email_status.get("oauth_configured"))
        connected = bool(email_status.get("connected"))
        safe_scope = email_status.get("requested_scope") == "https://www.googleapis.com/auth/gmail.readonly"
        stores_body = bool(email_status.get("stores_full_email_body"))
        if configured and connected and safe_scope and not stores_body:
            state, detail = "PASS", "OAuth configured and connected; Gmail read-only scope; full email bodies are not stored."
        else:
            state = "WARN"
            detail = f"OAuth configured={configured}; connected={connected}; read-only scope={safe_scope}; stores full body={stores_body}."
        checks.append(Check("Gmail connection + privacy", state, detail))

    queue_counts: dict[str, int] = {}
    for queue in ("pending", "approved", "ignored"):
        events = call(f"Gmail {queue} review queue", f"/api/email/events?review_status={queue}&limit=1", ("items", "total", "limit", "offset"))
        if events is not None:
            queue_counts[queue] = int(events.get("total", 0))
            checks.append(Check(f"Gmail {queue} review queue", "PASS", f"Endpoint available; {queue_counts[queue]} event(s)."))
    if len(queue_counts) == 3:
        checks.append(Check("Gmail review workflow APIs", "PASS", "Pending, approved and ignored queues are all readable; no email sync or review action was triggered."))

    ai_status = call("Local AI status API", "/api/ai/status", ("provider", "available", "configured_model", "model_installed"))
    if ai_status is not None:
        ai_ok = bool(ai_status.get("available")) and bool(ai_status.get("model_installed"))
        checks.append(Check("Local AI / Ollama", "PASS" if ai_ok else "WARN", f"available={ai_status.get('available')}; model={ai_status.get('configured_model')}; installed={ai_status.get('model_installed')}."))

    checks.extend(check_static_files(root, base_url))
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only JobPilot local stack verification.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="FastAPI base URL (default: http://127.0.0.1:8000).")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]), help="JobPilot project root.")
    parser.add_argument("--timeout", type=float, default=4.0, help="Per-request timeout in seconds.")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    print("JobPilot — Local Stack Preflight (READ ONLY)")
    print(f"Project root : {root}")
    print(f"API base URL : {args.base_url.rstrip('/')}")
    print("No Gmail sync, OAuth, application update, or database write will be performed.\n")

    results = run_checks(args.base_url, root, args.timeout)
    for item in results:
        print(f"[{item.status:4}] {item.name}: {item.detail}")

    passed = sum(item.status == "PASS" for item in results)
    warned = sum(item.status == "WARN" for item in results)
    failed = sum(item.status == "FAIL" for item in results)
    critical_failed = any(item.status == "FAIL" and item.critical for item in results)
    print("\nSummary")
    print(f"  Passed   : {passed}")
    print(f"  Warnings : {warned}")
    print(f"  Failed   : {failed}")
    if critical_failed:
        print("RESULT: BLOCKED — fix failed local services/files before live workflow testing.")
        return 1
    if warned:
        print("RESULT: AVAILABLE WITH WARNINGS — review optional integrations before the live workflow test.")
    else:
        print("RESULT: LOCAL STACK CHECKS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
