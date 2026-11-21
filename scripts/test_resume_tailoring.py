"""Tests for what tailoring does (ordering, matching skills, one page) and that the layout copies the master's style.

Uses a made-up resume (scripts/test_resume_parser_layouts.SAMPLE), a temporary store and no personal data.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
from pathlib import Path

_DB = tempfile.TemporaryDirectory()
os.environ["JOBPILOT_DATABASE_PATH"] = str(Path(_DB.name) / "tailoring.db")

from docx import Document
from pypdf import PdfReader

from app.resume.evidence_selector import ResumeEvidenceSelector
from app.resume.evidence_store import MasterResumeEvidenceStore
from app.resume.resume_builder import build_tailored_resume
from app.resume.resume_layout import STYLE, build_layout
from app.resume.resume_pdf_builder import _fonts, build_tailored_resume_pdf, page_count
from app.resume.tailoring_logic import JobTerms, order_bullets, tailor_for_job
from scripts.test_resume_parser_layouts import SAMPLE


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def terms(required=(), preferred=(), inferred=()) -> JobTerms:
    return JobTerms({"signals": {"required_skills": list(required), "preferred_skills": list(preferred), "inferred_job_technologies": list(inferred)}})


def fixture(tmp: Path, resume_text: str = SAMPLE):
    resume = tmp / "resume.txt"
    resume.write_text(resume_text, encoding="utf-8")
    store_path = tmp / "store.json"
    store = MasterResumeEvidenceStore(store_path)
    store.build_from_file(resume)
    for item in store.load()["evidence"]:
        store.set_verified(item["evidence_id"], True, "test")
    data = store.load()
    selection = ResumeEvidenceSelector(store_path).select_for_job(
        job_title="Backend Engineer", job_description="Build services with Node.js, Kafka and Redis.",
        required_skills=["Node.js", "Kafka"], preferred_skills=["Redis"])
    return selection, data


def test_matching_bullets_go_first_and_dependents_stay_attached() -> None:
    bullets = [
        "Wrote unit tests for the billing screens.",
        "Built a payments pipeline with Kafka and Node.js for refunds.",
        "Added alerting to that pipeline with a dead-letter topic.",
        "Cleaned up the wiki.",
    ]
    ordered, moved = order_bullets(bullets, terms(required=["Kafka", "Node.js"]))
    check(ordered[:2] == [bullets[1], bullets[2]], f"the matching bullet and the one that refers back to it lead: {ordered}")
    check(sorted(ordered) == sorted(bullets) and moved > 0, "nothing is added or removed, only moved")
    same, none_moved = order_bullets(bullets, terms(required=["Haskell"]))
    check(same == bullets and none_moved == 0, "with no match the master's order is kept")


def test_aliases_count_as_matches() -> None:
    score, matched = terms(required=["REST APIs"]).score("Built a REST API for orders.")
    check(score == 3 and matched == ["REST APIs"], (score, matched))
    check(terms(required=["Kafka"]).score("Moved events to Apache Kafka (KafkaJS) topics.")[0] == 3, "KafkaJS wording matches Kafka")
    check(terms(required=["Java"]).score("Wrote JavaScript tests.")[0] == 0, "Java does not match inside JavaScript")


def test_tailoring_orders_adds_the_match_line_and_changes_nothing_else() -> None:
    with tempfile.TemporaryDirectory() as folder:
        selection, store = fixture(Path(folder))
        content = tailor_for_job(selection, store)
        shown = " ".join(content.matches)
        check("Kafka" in shown and "Node.js" in shown and "Redis" in shown, content.matches)
        check(any("Relevant to this role" in line for line in content.changes), content.changes)
        check(content.changes[-1].startswith("The wording of every bullet is exactly"), "the report states nothing was rewritten")
        original = {b for r in store["evidence"] if r["category"] in ("experience", "project") for b in (r["metadata"].get("bullets") or [])}
        printed = {b for r in content.records if r["category"] in ("experience", "project") for b in (r["metadata"].get("bullets") or [])}
        check(printed <= original, "every printed bullet is a bullet from the master resume")
        layout = build_layout(content.records, store["candidate"], content.matches)
        titles = [section.title for section in layout.sections]
        check(titles == ["Summary", "Experience", "Projects", "Technical Skills", "Education", "Certifications", "Achievements"], titles)
        skills = [item for section in layout.sections if section.title == "Technical Skills" for item in section.items]
        first = "".join(run.text for run in skills[0].runs)
        check(first.startswith("Relevant to this role: ") and "Kafka" in first, first)
        grouped = ["".join(run.text for run in line.runs) for line in skills[1:]]
        check(any(g.startswith("Languages: ") for g in grouped) and any(g.startswith("Backend and Cloud: ") for g in grouped), grouped)


def test_long_resume_is_trimmed_to_one_page_without_breaking_a_bullet() -> None:
    extra = "\n".join(f"Delivered feature number {n} for the payments platform, covering retries, auditing and alerting for operators." for n in range(1, 31))
    long_resume = SAMPLE.replace("Wrote 300+ unit tests across 6 services to meet the 80% coverage gate.",
                                 "Wrote 300+ unit tests across 6 services to meet the 80% coverage gate.\n" + extra)
    with tempfile.TemporaryDirectory() as folder:
        selection, store = fixture(Path(folder), long_resume)
        untrimmed = tailor_for_job(selection, store, fit_one_page=False)
        check(page_count(build_layout(untrimmed.records, store["candidate"], untrimmed.matches)) > 1, "the long resume does not fit one page by itself")
        content = tailor_for_job(selection, store)
        check(page_count(build_layout(content.records, store["candidate"], content.matches)) == 1, "after trimming it does")
        check(any(line.startswith("Dropped ") for line in content.changes), content.changes)
        job = next(r for r in content.records if r["category"] == "experience")
        check(len(job["metadata"]["bullets"]) >= 3, "never below three bullets per job")
        for bullet in job["metadata"]["bullets"]:
            check(bullet.endswith("."), f"bullets are whole sentences: {bullet!r}")


def test_pdf_and_docx_follow_the_master_style() -> None:
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        selection, store = fixture(folder)
        docx_path, pdf_path = folder / "t.docx", folder / "t.pdf"
        build_tailored_resume(selection, store, docx_path)
        build_tailored_resume_pdf(selection, store, pdf_path)

        reader = PdfReader(str(pdf_path))
        width, height = float(reader.pages[0].mediabox.width), float(reader.pages[0].mediabox.height)
        check((round(width), round(height)) == (595, 842), f"A4 like the master, got {width}x{height}")
        text = reader.pages[0].extract_text()
        check("Languages:" in text and "Relevant to this role:" in text and "SUMMARY" in text, "the master's sections and grouped skills")
        check("Languages:Java" not in text.replace(" ", "") or "Languages: " in text, "a space after each skills label")

        doc = Document(str(docx_path))
        section = doc.sections[0]
        check((round(section.page_width.mm), round(section.page_height.mm)) == (210, 297), "DOCX is A4")
        fonts = {run.font.name for p in doc.paragraphs for run in p.runs if run.text.strip()}
        sizes = {round(run.font.size.pt, 1) for p in doc.paragraphs for run in p.runs if run.text.strip() and run.font.size}
        check(fonts == {"Calibri"}, fonts)
        # Word stores sizes in half points, so 9.6 and 10.6 pt become 9.5 and 10.5 pt in the DOCX.
        half = lambda value: round(value * 2) / 2  # noqa: E731
        check(sizes == {half(STYLE["name_size"]), half(STYLE["body_size"]), half(STYLE["heading_size"])}, sizes)
        headings = [p.text for p in doc.paragraphs if p.text.isupper() and len(p.text) < 25]
        check(headings[1:4] == ["SUMMARY", "EXPERIENCE", "PROJECTS"], headings)  # headings[0] is the (upper case) name
        labels = [p.text for p in doc.paragraphs if p.text.startswith("Languages:")]
        check(labels and labels[0].startswith("Languages: "), "a space after the label in the DOCX too")


def test_confirmed_skills_with_symbols_do_not_collide_and_still_print() -> None:
    """Regression: "C++" and "C#" both became the id "...-c", the second replaced the first, and generation failed
    with "selection report is stale for 'C#'". Confirmed skills must keep separate ids and print on the resume."""
    from app.api import main as api_main

    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        selection, store = fixture(folder)
        selection = ResumeEvidenceSelector(folder / "store.json").select_for_job(
            job_title="Software Engineer", job_description="Build services in Java, C++ and C#.",
            required_skills=["Java", "C++", "C#"], preferred_skills=[])
        request = api_main.EvidenceSelectionRequest(
            job_title="Software Engineer", job_description="Build services in Java, C++ and C#.",
            required_skills=["Java", "C++", "C#"], confirmed_skills=["C++", "C#"])
        selection, store = api_main._apply_resume_choices(selection, store, request)
        ids = [item["evidence_id"] for item in selection["selected_evidence"] if item.get("user_confirmed")]
        check(len(ids) == 2 and len(set(ids)) == 2, f"two confirmed skills, two different ids: {ids}")
        docx_path, pdf_path = folder / "c.docx", folder / "c.pdf"
        build_tailored_resume(selection, store, docx_path)  # used to raise "stale"
        build_tailored_resume_pdf(selection, store, pdf_path)
        text = chr(10).join(p.text for p in Document(str(docx_path)).paragraphs)
        languages = next(line for line in text.splitlines() if line.startswith("Languages:"))
        check("C++" in languages and "C#" in languages, f"confirmed languages join the Languages line: {languages}")
        pdf_text = PdfReader(str(pdf_path)).pages[0].extract_text()
        check("C++" in pdf_text and "C#" in pdf_text, "and they print in the PDF too")


def test_font_is_calibri_when_available() -> None:
    fonts = _fonts()
    if fonts["family"] == "Helvetica":
        print("  (Calibri/Carlito not installed here; the Helvetica fallback was used)")
        return
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        selection, store = fixture(folder)
        pdf_path = folder / "t.pdf"
        build_tailored_resume_pdf(selection, store, pdf_path)
        used = {name for page in PdfReader(str(pdf_path)).pages for name in page["/Resources"]["/Font"].values() for name in [str(name.get_object().get("/BaseFont"))]}
        check(any("Calibri" in name or "Carlito" in name for name in used), used)


TESTS = [
    ("Matching bullets go first and dependents stay attached", test_matching_bullets_go_first_and_dependents_stay_attached),
    ("Aliases count as matches, substrings do not", test_aliases_count_as_matches),
    ("Tailoring orders, adds the match line and changes no wording", test_tailoring_orders_adds_the_match_line_and_changes_nothing_else),
    ("A long resume is trimmed to one page without breaking a bullet", test_long_resume_is_trimmed_to_one_page_without_breaking_a_bullet),
    ("PDF and DOCX follow the master style", test_pdf_and_docx_follow_the_master_style),
    ("Confirmed skills with symbols keep separate ids and print", test_confirmed_skills_with_symbols_do_not_collide_and_still_print),
    ("The PDF uses Calibri when it is installed", test_font_is_calibri_when_available),
]


def main() -> int:
    failed = 0
    for name, test in TESTS:
        try:
            test()
            print(f"PASS - {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL - {name}: {type(exc).__name__}: {exc}")
    print(f"\nUnit tests: {len(TESTS) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
