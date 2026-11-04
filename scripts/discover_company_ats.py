from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.collectors.company_ats_discovery import discover_company_source

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / "data" / "target_companies.json"
OUTPUT_PATH = PROJECT_ROOT / "data" / "company_source_discovery.json"


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    companies = payload.get("companies")
    if not isinstance(companies, list):
        raise ValueError("target_companies.json must contain a companies array")
    if len(companies) != 30:
        raise ValueError(f"Expected exactly 30 target companies, found {len(companies)}")
    return payload


def run_discovery(*, only: set[str] | None = None, timeout: int = 20) -> dict[str, Any]:
    registry = load_registry()
    results = []
    for company in registry["companies"]:
        if only and company["id"] not in only:
            continue
        result = discover_company_source(company, timeout=timeout)
        results.append(result)
        print(f"[{result['status']}] {company['name']}: {len(result.get('sources', []))} ATS source(s)")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_registry": str(REGISTRY_PATH.name),
        "results": results,
        "note": "Discovery is evidence only. Review official-domain ownership and board identifiers before enabling a source for ingestion.",
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved discovery report: {OUTPUT_PATH}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover public ATS links on the 30 official company career pages.")
    parser.add_argument("--only", action="append", default=[], help="Company ID; repeat to restrict discovery.")
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()
    try:
        run_discovery(only=set(args.only) if args.only else None, timeout=args.timeout)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Discovery failed: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
