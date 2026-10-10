from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.resume.evidence_store import DEFAULT_STORE_PATH
from app.resume.resume_builder import (
    ResumeBuildError,
    build_tailored_resume_from_files,
    default_output_path,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SELECTION = (
    PROJECT_ROOT
    / "data"
    / "raw_jobs"
    / "frontend_evidence_selection.json"
)

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "generated_resumes"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate an ATS-friendly DOCX resume from a JobPilot "
            "evidence-selection report. Only currently user-verified "
            "evidence is accepted."
        )
    )

    parser.add_argument(
        "--selection",
        type=Path,
        default=DEFAULT_SELECTION,
        help=f"Selection JSON file (default: {DEFAULT_SELECTION})",
    )

    parser.add_argument(
        "--store",
        type=Path,
        default=DEFAULT_STORE_PATH,
        help=f"Master evidence JSON (default: {DEFAULT_STORE_PATH})",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Output DOCX path. Defaults to "
            "data/generated_resumes/Tailored_<job>.docx"
        ),
    )

    parser.add_argument(
        "--audit-output",
        type=Path,
        default=None,
        help="Optional JSON provenance/audit sidecar path.",
    )

    args = parser.parse_args()

    # Read the job title to build a descriptive default output filename.
    try:
        selection_text = args.selection.read_text(encoding="utf-8")
        selection_data = json.loads(selection_text)

        if not isinstance(selection_data, dict):
            raise ValueError("Selection JSON must be an object.")

        job_title = str(
            selection_data.get("job", {}).get(
                "title", "Job Application"
            )
        )

    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(f"Cannot read selection report: {exc}")

    output_path = args.output or default_output_path(
        job_title,
        DEFAULT_OUTPUT_DIR,
    )

    audit_path = args.audit_output

    if audit_path is None:
        audit_path = output_path.with_suffix(".audit.json")

    try:
        result = build_tailored_resume_from_files(
            args.selection,
            args.store,
            output_path,
            audit_path=audit_path,
        )

    except (OSError, ValueError, ResumeBuildError) as exc:
        parser.error(str(exc))

    print("=" * 64)
    print("JobPilot Tailored Resume Generator")
    print("=" * 64)
    print(f"Job title : {job_title}")
    print(f"Selection : {args.selection.resolve()}")
    print(f"Store     : {args.store.resolve()}")
    print(f"Resume    : {result}")
    print(f"Audit     : {Path(audit_path).resolve()}")
    print("Source claims are not rewritten or invented.")
    print("SUCCESS: Tailored resume generated.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())