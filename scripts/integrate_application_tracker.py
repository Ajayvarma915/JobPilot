from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path


def make_backup(path: Path) -> Path:
    suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(
        f"{path.name}.before_application_tracker_{suffix}.bak"
    )
    shutil.copy2(path, backup)
    return backup


def main() -> None:
    root = Path.cwd().resolve()

    api_path = root / "app" / "api" / "main.py"
    tracker_path = root / "app" / "applications" / "tracker.py"
    init_path = root / "app" / "applications" / "__init__.py"

    if not api_path.is_file():
        raise SystemExit(
            "Run from the JobPilot project root; "
            "app/api/main.py was not found."
        )

    if not tracker_path.is_file() or not init_path.is_file():
        raise SystemExit(
            "Copy tracker.py and __init__.py "
            "into app/applications/ first."
        )

    source = api_path.read_text(encoding="utf-8")
    original = source

    import_line = (
        "from app.applications.tracker "
        "import router as applications_router"
    )

    if import_line not in source:
        import_marker = "from fastapi.responses import FileResponse"

        if import_marker not in source:
            raise SystemExit(
                "Could not find the FastAPI FileResponse import. "
                "API file left unchanged."
            )

        source = source.replace(
            import_marker,
            import_marker + "\n" + import_line,
            1,
        )

    include_line = "app.include_router(applications_router)"

    if include_line not in source:
        middleware_marker = "app.add_middleware("

        if middleware_marker not in source:
            raise SystemExit(
                "Could not find app.add_middleware. "
                "API file left unchanged."
            )

        source = source.replace(
            middleware_marker,
            include_line + "\n\n" + middleware_marker,
            1,
        )

    methods_match = re.search(
        r"allow_methods\s*=\s*\[([^\]]*)\]",
        source,
    )

    if not methods_match:
        raise SystemExit(
            "Could not find the CORS allow_methods list. "
            "API file left unchanged."
        )

    methods_text = methods_match.group(1)

    if '"PATCH"' not in methods_text and "'PATCH'" not in methods_text:
        clean_methods = methods_text.rstrip().rstrip(",").rstrip()

        source = (
            source[:methods_match.start(1)]
            + clean_methods
            + ', "PATCH"'
            + source[methods_match.end(1):]
        )

    if source == original:
        print(
            "Application tracker router is already integrated; "
            "no changes needed."
        )
        return

    backup = make_backup(api_path)
    api_path.write_text(source, encoding="utf-8")

    print(f"Updated: {api_path}")
    print(f"Backup:  {backup}")
    print("Application tracker endpoints are now included in FastAPI.")


if __name__ == "__main__":
    main()