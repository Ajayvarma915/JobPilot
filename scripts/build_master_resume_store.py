from __future__ import annotations

import argparse
from pathlib import Path

from app.resume.evidence_store import (
    DEFAULT_RESUME_DIRECTORY,
    DEFAULT_STORE_PATH,
    MasterResumeEvidenceStore,
    discover_master_resume,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Parse a master resume and build a traceable JSON evidence store."
        )
    )

    parser.add_argument(
        "--resume",
        type=Path,
        help=(
            "Resume file to parse. If omitted, auto-select the only supported "
            "file in data/master_resume."
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_STORE_PATH,
        help=f"Output JSON path (default: {DEFAULT_STORE_PATH}).",
    )

    parser.add_argument(
        "--reset-review-status",
        action="store_true",
        help=(
            "Do not preserve existing user verification status when rebuilding "
            "the store."
        ),
    )

    args = parser.parse_args()

    try:
        if args.resume:
            resume_path = args.resume.expanduser().resolve()
        else:
            resume_path = discover_master_resume(DEFAULT_RESUME_DIRECTORY)

        store = MasterResumeEvidenceStore(args.output.expanduser().resolve())

        data = store.build_from_file(
            resume_path,
            preserve_review_status=not args.reset_review_status,
        )

    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))

    print("=" * 52)
    print("JobPilot Master Resume Evidence Store")
    print("=" * 52)
    print(f"Resume       : {data['source_resume']['file']}")
    print(f"SHA-256      : {data['source_resume']['sha256']}")
    print(f"Store        : {store.store_path}")
    print(f"Evidence rows: {data['evidence_count']}")
    print("Counts by category:")

    for category, count in data["counts_by_category"].items():
        print(f"  {category:<16} {count}")

    print("Review status: all new/changed records need review")
    print("SUCCESS: Master resume evidence store created.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())