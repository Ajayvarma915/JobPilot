from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.resume.evidence_selector import ResumeEvidenceSelector
from app.resume.evidence_store import DEFAULT_STORE_PATH


def _csv_values(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _read_description(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> str:
    if args.description is not None:
        return args.description.strip()

    if args.description_file is not None:
        try:
            return args.description_file.read_text(
                encoding="utf-8"
            ).strip()
        except OSError as exc:
            parser.error(f"Could not read description file: {exc}")

    parser.error("Provide either --description or --description-file.")
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Select verified master-resume evidence for a job description."
        )
    )
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE_PATH)
    parser.add_argument("--job-title", required=True)

    description = parser.add_mutually_exclusive_group(required=True)
    description.add_argument(
        "--description",
        help="Full job description text.",
    )
    description.add_argument(
        "--description-file",
        type=Path,
        help="UTF-8 text file containing the JD.",
    )

    parser.add_argument(
        "--required-skills",
        default="",
        help="Comma-separated required skills from the JD analysis.",
    )
    parser.add_argument(
        "--preferred-skills",
        default="",
        help="Comma-separated preferred skills from the JD analysis.",
    )
    parser.add_argument("--max-projects", type=int, default=3)
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for JSON selection results.",
    )
    args = parser.parse_args()

    jd_text = _read_description(args, parser)
    selector = ResumeEvidenceSelector(args.store)

    try:
        result = selector.select_for_job(
            job_title=args.job_title,
            job_description=jd_text,
            required_skills=_csv_values(args.required_skills),
            preferred_skills=_csv_values(args.preferred_skills),
            max_projects=max(0, args.max_projects),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    print("=" * 68)
    print("JobPilot Resume Evidence Selection")
    print("=" * 68)
    print(f"Job title            : {result['job']['title']}")
    print(f"Verified selected    : {result['counts']['verified_selected']}")
    print(
        "Relevant review queue: "
        f"{result['counts']['unverified_relevant_for_review']}"
    )
    print(f"Required skills      : {result['coverage']['required_skills']}")
    print(
        "Verified covered     : "
        f"{', '.join(result['coverage']['verified_covered']) or 'None'}"
    )
    print(
        "Awaiting review      : "
        f"{', '.join(result['coverage']['awaiting_evidence_review']) or 'None'}"
    )
    print(
        "Not found            : "
        f"{', '.join(result['coverage']['not_found_in_evidence']) or 'None'}"
    )

    print("\nVerified evidence eligible for resume:")
    if not result["selected_evidence"]:
        print("  None yet. Review and verify relevant evidence first.")

    for item in result["selected_evidence"]:
        print(
            f"  [{item['category']}] {item['title']} "
            f"(score {item['score']})"
        )
        print(f"    Why: {'; '.join(item['reason'])}")
        print(
            f"    Source: {item['source'].get('file')} / "
            f"{item['source'].get('section')}"
        )

    print(
        "\nRelevant evidence that still needs review "
        "(not eligible for resume):"
    )

    if not result["review_queue"]:
        print("  None.")

    for item in result["review_queue"][:20]:
        print(
            f"  [{item['category']}] {item['title']} "
            f"(score {item['score']})"
        )
        print(f"    Why: {'; '.join(item['reason'])}")

    if args.output:
        output_path = args.output.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"\nJSON report saved: {output_path}")

    print(
        "\nSafety: only user-verified evidence is included "
        "in selected_evidence."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())