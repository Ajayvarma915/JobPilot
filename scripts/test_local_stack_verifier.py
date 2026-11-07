from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from scripts.verify_local_stack import run_checks


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        query = parse_qs(urlparse(self.path).query)
        payloads = {
            "/api/health": {"status": "ok", "database": "connected", "jobs_available": 10, "companies_available": 3},
            "/api/dashboard/stats": {"total_jobs": 10, "active_jobs": 8, "total_companies": 3},
            "/api/applications/stats": {"total": 2, "needs_action": 1, "by_status": {"saved": 1}},
            "/api/applications": {"items": [], "total": 2, "limit": 1, "offset": 0},
            "/api/email/status": {"provider": "gmail", "oauth_configured": True, "connected": True, "requested_scope": "https://www.googleapis.com/auth/gmail.readonly", "stores_full_email_body": False},
            "/api/ai/status": {"provider": "ollama", "available": True, "configured_model": "gemma3:4b", "model_installed": True},
        }
        if path == "/api/email/events":
            payload = {"items": [], "total": 0, "limit": 1, "offset": 0}
        else:
            payload = payloads.get(path)
        if payload is None:
            self.send_error(404)
            return
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args):
        pass


class LocalStackVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=2)
        cls.server.server_close()

    def test_read_only_preflight_reports_all_local_components(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dist = root / "frontend" / "dist"
            (dist / "assets").mkdir(parents=True)
            (dist / "assets" / "app.js").write_text("// test", encoding="utf-8")
            (dist / "assets" / "app.css").write_text("/* test */", encoding="utf-8")
            (dist / "index.html").write_text('<script src="/assets/app.js"></script><link href="/assets/app.css" rel="stylesheet">', encoding="utf-8")
            extension = root / "browser_extension" / "jobpilot-form-assistant"
            extension.mkdir(parents=True)
            (extension / "manifest.json").write_text(json.dumps({"manifest_version": 3, "host_permissions": [f"{self.base_url}/*"]}), encoding="utf-8")
            (extension / "popup.js").write_text(f'const API_BASE = "{self.base_url}";', encoding="utf-8")
            (extension / "popup.html").write_text("<html></html>", encoding="utf-8")

            checks = run_checks(self.base_url, root, timeout=2)
            statuses = [check.status for check in checks]
            self.assertTrue(checks)
            self.assertTrue(all(status == "PASS" for status in statuses), checks)
            self.assertTrue(any(check.name == "Gmail pending review queue" for check in checks))
            self.assertTrue(any(check.name == "Chrome extension configuration" for check in checks))


if __name__ == "__main__":
    unittest.main(verbosity=2)
