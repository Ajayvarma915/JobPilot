from __future__ import annotations

import re
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer

from app.resume.resume_builder import ResumeBuildError, _validated_records
from app.resume.resume_layout import STYLE, Bullet, Line, Run, build_layout

# Calibri is the master resume's font. It is used from the copy installed with Windows/Office (never bundled
# here). Carlito is the metric-compatible open font on Linux. Without either, the PDF falls back to Helvetica
# and says so in its log, so the file still builds.
_FONT_SETS = (
    ("C:/Windows/Fonts", ("calibri.ttf", "calibrib.ttf", "calibrii.ttf", "calibriz.ttf")),
    ("/usr/share/fonts/truetype/crosextra", ("Carlito-Regular.ttf", "Carlito-Bold.ttf", "Carlito-Italic.ttf", "Carlito-BoldItalic.ttf")),
    ("/usr/share/fonts/truetype/carlito", ("Carlito-Regular.ttf", "Carlito-Bold.ttf", "Carlito-Italic.ttf", "Carlito-BoldItalic.ttf")),
    ("/Library/Fonts", ("Calibri.ttf", "Calibri Bold.ttf", "Calibri Italic.ttf", "Calibri Bold Italic.ttf")),
)


@lru_cache(maxsize=1)
def _fonts() -> dict[str, str]:
    """Register the master's font family once and return the font names to use."""
    for folder, files in _FONT_SETS:
        paths = [Path(folder) / name for name in files]
        if all(path.is_file() for path in paths):
            names = {"regular": "JPResume", "bold": "JPResume-Bold", "italic": "JPResume-Italic", "bolditalic": "JPResume-BoldItalic"}
            try:
                for key, path in zip(("regular", "bold", "italic", "bolditalic"), paths):
                    pdfmetrics.registerFont(TTFont(names[key], str(path)))
                pdfmetrics.registerFontFamily("JPResume", normal=names["regular"], bold=names["bold"], italic=names["italic"], boldItalic=names["bolditalic"])
                return {**names, "family": "Calibri-compatible"}
            except Exception:  # noqa: BLE001 - a font file that cannot be read must not stop the resume
                continue
    return {"regular": "Helvetica", "bold": "Helvetica-Bold", "italic": "Helvetica-Oblique", "bolditalic": "Helvetica-BoldOblique", "family": "Helvetica"}


def _markup(runs: list[Run]) -> str:
    """Runs to ReportLab's mini-HTML. Text is escaped; newlines never become markup."""
    out = []
    for run in runs:
        # Collapse runs of spaces and newlines, but keep ONE space at either edge ("Languages: " + "Java").
        text = escape(re.sub(r"\s+", " ", run.text), quote=False)
        if not text.strip():
            continue
        if run.bold and run.italic:
            text = f"<b><i>{text}</i></b>"
        elif run.bold:
            text = f"<b>{text}</b>"
        elif run.italic:
            text = f"<i>{text}</i>"
        colour = {"muted": STYLE["muted"], "link": STYLE["link"]}.get(run.kind)
        out.append(f'<font color="{colour}">{text}</font>' if colour else text)
    return "".join(out)


def _styles() -> dict[str, ParagraphStyle]:
    font = _fonts()
    base = getSampleStyleSheet()["Normal"]
    text = colors.HexColor(STYLE["text"])
    common = dict(parent=base, fontName=font["regular"], fontSize=STYLE["body_size"], leading=STYLE["body_leading"],
                  textColor=text, splitLongWords=True, wordWrap="LTR")
    return {
        "name": ParagraphStyle("JPName", **{**common, "fontName": font["bold"], "fontSize": STYLE["name_size"], "leading": STYLE["name_leading"],
                                            "alignment": TA_CENTER, "keepWithNext": True}),
        "contact": ParagraphStyle("JPContact", **{**common, "alignment": TA_CENTER}),
        "section": ParagraphStyle("JPSection", **{**common, "fontName": font["bold"], "fontSize": STYLE["heading_size"], "leading": STYLE["heading_leading"],
                                                  "alignment": TA_LEFT, "spaceBefore": 6, "spaceAfter": 0.5, "keepWithNext": True}),
        "body": ParagraphStyle("JPBody", **common),
        "entry": ParagraphStyle("JPEntry", **{**common, "fontName": font["bold"], "spaceBefore": 1.5, "keepWithNext": True}),
        "sub": ParagraphStyle("JPSub", **{**common, "fontName": font["italic"], "keepWithNext": True}),
        "bullet": ParagraphStyle("JPBullet", **{**common, "leftIndent": STYLE["bullet_indent"], "firstLineIndent": 0, "bulletIndent": 1.5,
                                                "bulletFontName": font["regular"], "bulletFontSize": STYLE["body_size"]}),
    }


def build_tailored_resume_pdf(
    selection: dict[str, Any],
    store: dict[str, Any],
    output_path: str | Path,
) -> Path:
    """Create a selectable-text, one-column PDF in the master resume's style from currently verified evidence.

    The same validation as the DOCX builder runs first. Content is not generated or rewritten; verified
    statements are only laid out. No photos, tables, columns, icons or text boxes, so it parses reliably.
    """
    candidate = store.get("candidate")
    if not isinstance(candidate, dict) or not candidate.get("name"):
        raise ResumeBuildError("Evidence store has no candidate name.")

    from app.resume.tailoring_logic import tailor_for_job

    content = tailor_for_job(selection, store)
    layout = build_layout(content.records, candidate, content.matches)
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    title = f"Tailored Resume - {selection.get('job', {}).get('title', 'Job Application')}"
    _draw_pdf(layout, str(output), title)
    return output


def page_count(layout: Any) -> int:
    """How many pages this layout needs (drawn in memory)."""
    import io

    buffer = io.BytesIO()
    return _draw_pdf(layout, buffer, "measure")


def _draw_pdf(layout: Any, target: Any, title: str) -> int:
    styles = _styles()

    story: list[Any] = [Paragraph(_markup([Run(layout.name)]), styles["name"])]
    for line in layout.contact:
        story.append(Paragraph(_markup(line), styles["contact"]))

    for section in layout.sections:
        heading = [
            Paragraph(escape(section.title.upper()), styles["section"]),
            HRFlowable(width="100%", thickness=STYLE["rule_width"], color=colors.HexColor(STYLE["rule"]), spaceBefore=0.5, spaceAfter=2.5),
        ]
        items = list(section.items)
        # Keep a heading with the first line under it, never alone at the bottom of a page.
        first = items.pop(0) if items else None
        story.append(KeepTogether(heading + ([_paragraph_for(first, styles)] if first else [])))
        story.extend(_paragraph_for(item, styles) for item in items)

    document = SimpleDocTemplate(
        target,
        pagesize=A4,
        # ReportLab's frame adds 6 pt of padding on every side; remove it so the margins are the master's.
        leftMargin=STYLE["margin_left"] - 6,
        rightMargin=STYLE["margin_right"] - 6,
        topMargin=STYLE["margin_top"] - 6,
        bottomMargin=STYLE["margin_bottom"] - 6,
        title=title[:240],
        author=layout.name or "JobPilot",
        subject="Resume generated from user-verified evidence",
    )
    document.build(story)
    return int(document.page)


def _paragraph_for(item: Line | Bullet, styles: dict[str, ParagraphStyle]) -> Paragraph:
    if isinstance(item, Bullet):
        return Paragraph(_markup(item.runs), styles["bullet"], bulletText="\u2022")
    return Paragraph(_markup(item.runs), styles[item.style if item.style in styles else "body"])


__all__ = ["build_tailored_resume_pdf"]
