from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from app.collectors.company_ats_discovery import integration_config_from_source

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / "data" / "target_companies.json"
REPORT_PATH = PROJECT_ROOT / "data" / "company_source_discovery.json"


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path.name}")
    return payload


def build_candidates(registry: dict[str, Any], report: dict[str, Any]) -> list[dict[str, Any]]:
    companies = {str(row.get("id")): row for row in registry.get("companies", [])}
    candidates: list[dict[str, Any]] = []
    for result in report.get("results", []):
        company_id = str(result.get("company_id") or "")
        company = companies.get(company_id)
        if not company:
            continue
        current = company.get("integration") or {}
        if current.get("verified") or current.get("status") == "active":
            continue
        for source in result.get("sources", []):
            config = integration_config_from_source(source)
            if config:
                candidates.append({
                    "company_id": company_id,
                    "company": company.get("name"),
                    "config": config,
                })
                break
    return candidates


def apply_candidates(registry: dict[str, Any], candidates: list[dict[str, Any]]) -> int:
    by_id = {str(row.get("id")): row for row in registry.get("companies", [])}
    applied = 0
    for candidate in candidates:
        company = by_id.get(candidate["company_id"])
        if not company:
            continue
        current = company.get("integration") or {}
        if current.get("verified") or current.get("status") == "active":
            continue
        company["integration"] = candidate["config"]
        applied += 1
    return applied


def main() -> int:
    parser = argparse.ArgumentParser(description="Map ATS links detected on official career pages into the 30-company registry.")
    parser.add_argument("--apply", action="store_true", help="Write candidate mappings to target_companies.json (they remain unverified).")
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    args = parser.parse_args()

    try:
        registry = _read_json(args.registry)
        report = _read_json(args.report)
        if len(registry.get("companies", [])) != 30:
            raise ValueError("Expected exactly 30 companies in target registry")
        candidates = build_candidates(registry, report)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        return 1

    print(f"Detected supported ATS mappings ready to configure: {len(candidates)}")
    for item in candidates:
        print(f"  {item['company_id']}: {item['config']['provider']} -> configured_needs_live_validation")

    if not args.apply:
        print("\nNo files changed. Review the list, then rerun with --apply to write these unverified mappings.")
        return 0

    backup = args.registry.with_suffix(args.registry.suffix + ".before_discovery.bak")
    if not backup.exists():
        shutil.copy2(args.registry, backup)
    applied = apply_candidates(registry, candidates)
    args.registry.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nApplied {applied} mapping(s). Backup: {backup}")
    print("Mappings remain unverified. Use --include-unverified --dry-run before enabling normal sync.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
