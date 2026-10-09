from __future__ import annotations

import argparse
from pathlib import Path

from app.resume.evidence_store import (
    DEFAULT_STORE_PATH,
    MasterResumeEvidenceStore,
)


def _clip(text: str, limit: int = 360) -> str:
    cleaned = " ".join(text.split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 3] + "..."


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Review extracted resume evidence before it can be "
            "used in tailored resumes."
        )
    )
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE_PATH)
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="List evidence and review statuses without prompting.",
    )
    args = parser.parse_args()

    store = MasterResumeEvidenceStore(args.store)

    try:
        data = store.load()
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    pending = [
        item
        for item in data["evidence"]
        if not item.get("review", {}).get("user_verified", False)
    ]

    verified_count = len(data["evidence"]) - len(pending)

    print("=" * 64)
    print("JobPilot Master Resume Evidence Review")
    print("=" * 64)
    print(f"Store   : {store.store_path}")
    print(f"Records : {len(data['evidence'])}")
    print(f"Verified: {verified_count}")
    print(f"Pending : {len(pending)}")
    print(
        "\nVerification means you have checked the record "
        "against your resume."
    )

    if args.list_only:
        for index, item in enumerate(data["evidence"], start=1):
            status = item.get("review", {}).get(
                "status", "needs_review"
            )
            print(
                f"{index:02}. [{status}] {item['category']}: "
                f"{item['title']} | ID: {item['evidence_id']}"
            )
        return 0

    if not pending:
        print("\nAll records have already been verified.")
        return 0

    print(
        "\nFor each item, enter [v] to verify, [s] to skip, "
        "or [q] to quit.\n"
    )
    changed = 0

    for index, item in enumerate(pending, start=1):
        print("-" * 64)
        print(
            f"{index}/{len(pending)} | "
            f"{item['category'].upper()} | {item['title']}"
        )
        print(f"Statement: {_clip(item.get('statement', ''))}")

        source = item.get("source", {})
        print(
            f"Source   : {source.get('file', '')} / "
            f"{source.get('section', '')}"
        )
        print(
            f"Evidence : {_clip(source.get('text', ''), 520)}"
        )

        while True:
            try:
                choice = input(
                    "Verify [v], skip [s], quit [q]: "
                ).strip().casefold()
            except (EOFError, KeyboardInterrupt):
                print(
                    "\nReview interrupted; prior decisions are saved."
                )
                print(f"Verified during this run: {changed}")
                return 0

            if choice in {"v", "s", "q"}:
                break

            print("Please enter v, s, or q.")

        if choice == "q":
            break

        if choice == "s":
            continue

        note = "User approved during interactive resume evidence review."
        store.set_verified(
            item["evidence_id"],
            True,
            note=note,
        )
        changed += 1
        print("Saved: verified.\n")

    updated = store.load()
    verified_total = sum(
        1
        for item in updated["evidence"]
        if item.get("review", {}).get("user_verified", False)
    )

    print("\nReview summary")
    print(f"Verified in this run: {changed}")
    print(f"Verified total     : {verified_total}/{len(updated['evidence'])}")
    print(f"Remaining review   : {len(updated['evidence']) - verified_total}")
    print("Only verified records may be selected for resume tailoring.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())