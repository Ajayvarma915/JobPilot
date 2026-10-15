from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path


GENERATE_REPLACEMENT = '''@app.post("/api/resumes/generate", status_code=201)
def generate_resume(
    request: EvidenceSelectionRequest,
) -> dict[str, Any]:
    selection = _select_evidence(request)

    if not selection.get("selected_evidence"):
        raise HTTPException(
            status_code=409,
            detail=(
                "No verified evidence was selected for this job. "
                "Review the evidence queue or select a different job "
                "before generating a resume."
            ),
        )

    store_data = _load_evidence_store()
    slug = (
        re.sub(r"[^A-Za-z0-9]+", "_", request.job_title).strip("_")[:60]
        or "Job"
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"Tailored_{slug}_{timestamp}.docx"
    pdf_filename = f"Tailored_{slug}_{timestamp}.pdf"

    GENERATED_RESUMES_DIR.mkdir(parents=True, exist_ok=True)
    output_path = GENERATED_RESUMES_DIR / filename
    pdf_output_path = GENERATED_RESUMES_DIR / pdf_filename
    audit_path = output_path.with_suffix(".audit.json")

    try:
        build_tailored_resume(
            selection,
            store_data,
            output_path,
            audit_path=audit_path,
        )
        build_tailored_resume_pdf(
            selection,
            store_data,
            pdf_output_path,
        )
        evaluation = evaluate_generated_resume(
            docx_path=output_path,
            pdf_path=pdf_output_path,
            selection=selection,
            store=store_data,
        )
    except Exception as exc:
        # Do not leave partial or unchecked outputs presented as successful files.
        for generated_path in (output_path, pdf_output_path, audit_path):
            try:
                generated_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise HTTPException(
            status_code=422,
            detail=f"Could not generate and validate the tailored resume: {exc}",
        ) from exc

    return {
        "status": "created",
        "job_title": request.job_title,
        "resume_filename": filename,
        "resume_path": _relative_display_path(output_path),
        "audit_path": _relative_display_path(audit_path),
        "selected_evidence_count": len(selection["selected_evidence"]),
        "download_url": f"/api/resumes/{filename}/download",
        "pdf_filename": pdf_filename,
        "pdf_download_url": f"/api/resumes/{pdf_filename}/download",
        "evaluation": evaluation,
        "safety": {
            "verified_evidence_required": True,
            "claims_invented": False,
        },
    }
'''

DOWNLOAD_REPLACEMENT = '''@app.get("/api/resumes/{filename}/download")
def download_resume(filename: str) -> FileResponse:
    suffix = Path(filename).suffix.lower()
    if (
        filename in {".", ".."}
        or Path(filename).name != filename
        or suffix not in {".docx", ".pdf"}
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid resume filename. Only generated DOCX and PDF files can be downloaded.",
        )

    output_directory = GENERATED_RESUMES_DIR.resolve()
    output_path = (output_directory / filename).resolve()

    if output_path.parent != output_directory:
        raise HTTPException(
            status_code=400,
            detail="Invalid resume path.",
        )

    if not output_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Generated resume was not found.",
        )

    media_type = (
        "application/pdf"
        if suffix == ".pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return FileResponse(path=output_path, filename=filename, media_type=media_type)
'''


def backup_path(path: Path) -> Path:
    backup = path.with_name(f"{path.name}.before_resume_upgrade.bak")
    if backup.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = path.with_name(f"{path.name}.before_resume_upgrade_{stamp}.bak")
    return backup


def patch_api(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    generate_start = source.find('@app.post("/api/resumes/generate"')
    download_start = source.find('@app.get("/api/resumes/{filename}/download")')
    if generate_start < 0 or download_start < 0 or download_start <= generate_start:
        raise RuntimeError(
            "Could not identify the current resume API routes in app/api/main.py. "
            "No API file was changed. Please share your latest main.py so this can be adapted safely."
        )

    # Detect whether the route was already upgraded to make reruns safe.
    if "pdf_download_url" in source and "evaluate_generated_resume(" in source and ".pdf" in source[download_start:]:
        print("Resume API already contains PDF generation and quality evaluation; leaving it unchanged.")
        return

    end_generate = download_start
    next_route = source.find("\n@app.", download_start + 1)
    next_main_guard = source.find("\nif __name__ ==", download_start + 1)
    possible_ends = [position for position in (next_route, next_main_guard) if position >= 0]
    end_download = min(possible_ends) if possible_ends else len(source)

    updated = source[:generate_start] + GENERATE_REPLACEMENT + "\n\n" + source[download_start:download_start] + DOWNLOAD_REPLACEMENT + source[end_download:]
    # Add imports beside the project root setup so this works even when other
    # service imports in the user's current API file differ from older snapshots.
    import_marker = "PROJECT_ROOT = Path(__file__).resolve().parents[2]"
    if import_marker not in updated:
        raise RuntimeError("Could not find PROJECT_ROOT in app/api/main.py; no API file was changed.")
    extra_imports = (
        "from app.resume.resume_pdf_builder import build_tailored_resume_pdf\n"
        "from app.resume.resume_evaluator import evaluate_generated_resume\n\n\n"
    )
    if "from app.resume.resume_pdf_builder import build_tailored_resume_pdf" not in updated:
        updated = updated.replace(import_marker, extra_imports + import_marker, 1)

    # Ensure the replacement hasn't swallowed any expected pieces.
    for required in (
        "def generate_resume(",
        "build_tailored_resume_pdf(",
        "evaluate_generated_resume(",
        "def download_resume(",
        'suffix not in {".docx", ".pdf"}',
    ):
        if required not in updated:
            raise RuntimeError(f"Safety check failed after preparing API edit: missing {required!r}. No API file was changed.")

    backup = backup_path(path)
    shutil.copy2(path, backup)
    path.write_text(updated, encoding="utf-8")
    print(f"Updated: {path}")
    print(f"Backup:  {backup}")


def main() -> None:
    root = Path.cwd().resolve()
    api_file = root / "app" / "api" / "main.py"
    pdf_builder = root / "app" / "resume" / "resume_pdf_builder.py"
    evaluator = root / "app" / "resume" / "resume_evaluator.py"

    if not api_file.is_file():
        raise SystemExit(
            "Run this script from the JobPilot project root; app/api/main.py was not found."
        )
    if not pdf_builder.is_file() or not evaluator.is_file():
        raise SystemExit(
            "Copy resume_pdf_builder.py and resume_evaluator.py to app/resume/ before running this script."
        )

    try:
        patch_api(api_file)
        requirements = root / "requirements.txt"
        if requirements.is_file():
            current = requirements.read_text(encoding="utf-8")
            lower_lines = {line.strip().casefold() for line in current.splitlines() if line.strip() and not line.lstrip().startswith("#")}
            additions = []
            if not any(line.split("=", 1)[0].split("<", 1)[0].split(">", 1)[0].strip() == "reportlab" for line in lower_lines):
                additions.append("reportlab>=4.0")
            if not any(line.split("=", 1)[0].split("<", 1)[0].split(">", 1)[0].strip() == "pypdf" for line in lower_lines):
                additions.append("pypdf>=5.0")
            if additions:
                backup = backup_path(requirements)
                shutil.copy2(requirements, backup)
                updated_requirements = current.rstrip() + "\n" + "\n".join(additions) + "\n"
                requirements.write_text(updated_requirements, encoding="utf-8")
                print(f"Updated dependencies: {requirements}")
                print(f"Requirements backup: {backup}")
    except Exception as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
