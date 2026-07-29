"""Build the DOT technical and user manual as a polished PDF.

The editable source is DOT_TECHNICAL_AND_USER_MANUAL.md.  This renderer
implements the deliberately small Markdown subset used by that document and
keeps the build independent of browser/Pandoc installations.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = HERE / "DOT_TECHNICAL_AND_USER_MANUAL.md"
OUTPUT = ROOT / "output" / "pdf" / "DOT_Technical_and_User_Manual_v1.1.pdf"

PAGE_W, PAGE_H = A4
LEFT = 18 * mm
RIGHT = 16 * mm
TOP = 18 * mm
BOTTOM = 22 * mm
CONTENT_W = PAGE_W - LEFT - RIGHT

NAVY = colors.HexColor("#17365d")
BLUE = colors.HexColor("#2f75b5")
LIGHT_BLUE = colors.HexColor("#eef4fb")
MID_BLUE = colors.HexColor("#d9e7f5")
GREEN = colors.HexColor("#2e8b57")
ORANGE = colors.HexColor("#d97706")
PURPLE = colors.HexColor("#7030a0")
TEXT = colors.HexColor("#1f2937")
MUTED = colors.HexColor("#5f6b7a")
RULE = colors.HexColor("#cbd5e1")
CODE_BG = colors.HexColor("#f6f8fa")


def _register_fonts() -> tuple[str, str, str, str]:
    candidates = [
        (
            Path("C:/Windows/Fonts/aptos.ttf"),
            Path("C:/Windows/Fonts/aptosbd.ttf"),
            Path("C:/Windows/Fonts/aptosi.ttf"),
            Path("C:/Windows/Fonts/aptosbi.ttf"),
        ),
        (
            Path("C:/Windows/Fonts/calibri.ttf"),
            Path("C:/Windows/Fonts/calibrib.ttf"),
            Path("C:/Windows/Fonts/calibrii.ttf"),
            Path("C:/Windows/Fonts/calibriz.ttf"),
        ),
    ]
    for regular, bold, italic, bold_italic in candidates:
        if all(path.exists() for path in (regular, bold, italic, bold_italic)):
            pdfmetrics.registerFont(TTFont("DOTSans", str(regular)))
            pdfmetrics.registerFont(TTFont("DOTSans-Bold", str(bold)))
            pdfmetrics.registerFont(TTFont("DOTSans-Italic", str(italic)))
            pdfmetrics.registerFont(TTFont("DOTSans-BoldItalic", str(bold_italic)))
            pdfmetrics.registerFontFamily(
                "DOTSans",
                normal="DOTSans",
                bold="DOTSans-Bold",
                italic="DOTSans-Italic",
                boldItalic="DOTSans-BoldItalic",
            )
            return ("DOTSans", "DOTSans-Bold", "DOTSans-Italic", "DOTSans-BoldItalic")
    return ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique")


FONT, FONT_BOLD, FONT_ITALIC, FONT_BOLD_ITALIC = _register_fonts()


def _styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "body": ParagraphStyle(
            "DOTBody",
            parent=sample["BodyText"],
            fontName=FONT,
            fontSize=9.15,
            leading=12.2,
            textColor=TEXT,
            spaceAfter=5.0,
            allowWidows=0,
            allowOrphans=0,
        ),
        "small": ParagraphStyle(
            "DOTSmall",
            parent=sample["BodyText"],
            fontName=FONT,
            fontSize=7.6,
            leading=9.5,
            textColor=MUTED,
        ),
        "h2": ParagraphStyle(
            "DOTHeading1",
            parent=sample["Heading1"],
            fontName=FONT_BOLD,
            fontSize=16.5,
            leading=20,
            textColor=NAVY,
            spaceBefore=14,
            spaceAfter=7,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "DOTHeading2",
            parent=sample["Heading2"],
            fontName=FONT_BOLD,
            fontSize=12.3,
            leading=15,
            textColor=BLUE,
            spaceBefore=10,
            spaceAfter=5,
            keepWithNext=True,
        ),
        "h4": ParagraphStyle(
            "DOTHeading3",
            parent=sample["Heading3"],
            fontName=FONT_BOLD,
            fontSize=10.2,
            leading=13,
            textColor=PURPLE,
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "caption": ParagraphStyle(
            "DOTCaption",
            parent=sample["BodyText"],
            fontName=FONT_ITALIC,
            fontSize=7.7,
            leading=9.4,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceBefore=3,
            spaceAfter=8,
        ),
        "table": ParagraphStyle(
            "DOTTable",
            parent=sample["BodyText"],
            fontName=FONT,
            fontSize=7.3,
            leading=9.0,
            textColor=TEXT,
        ),
        "table_header": ParagraphStyle(
            "DOTTableHeader",
            parent=sample["BodyText"],
            fontName=FONT_BOLD,
            fontSize=7.3,
            leading=9.0,
            textColor=colors.white,
        ),
        "callout": ParagraphStyle(
            "DOTCallout",
            parent=sample["BodyText"],
            fontName=FONT,
            fontSize=8.7,
            leading=11.2,
            textColor=NAVY,
        ),
        "toc_title": ParagraphStyle(
            "DOTTOCTitle",
            parent=sample["Heading1"],
            fontName=FONT_BOLD,
            fontSize=22,
            leading=26,
            textColor=NAVY,
            spaceAfter=14,
        ),
    }


STYLES = _styles()


class ManualDocTemplate(BaseDocTemplate):
    def __init__(self, filename: str) -> None:
        super().__init__(
            filename,
            pagesize=A4,
            leftMargin=LEFT,
            rightMargin=RIGHT,
            topMargin=TOP,
            bottomMargin=BOTTOM,
            title="DOT - Dipole Optimization Tool: Technical Reference and User Manual",
            author="Mattia Elisei, INFN Milan and University of Rome La Sapienza",
            subject="Technical disclosure, optimization workflow, geometry constraints, and user guide",
            creator="DOT reproducible ReportLab manual build",
        )
        body = Frame(LEFT, BOTTOM, CONTENT_W, PAGE_H - TOP - BOTTOM, id="body")
        self.addPageTemplates(
            [
                PageTemplate(id="content", frames=[body], onPage=_page_chrome),
            ]
        )
        self._heading_counter = 0

    def beforeDocument(self) -> None:
        # multiBuild may lay the story out several times while resolving the
        # table of contents; stable bookmark keys are required on every pass.
        self._heading_counter = 0

    def afterFlowable(self, flowable: Flowable) -> None:
        if not isinstance(flowable, Paragraph):
            return
        level = getattr(flowable, "_toc_level", None)
        if level is None:
            return
        self._heading_counter += 1
        key = f"heading-{self._heading_counter}"
        text = flowable.getPlainText()
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(text, key, level=level, closed=level > 0)
        self.notify("TOCEntry", (level, text, self.page, key))


def _page_chrome(canvas: Canvas, doc: BaseDocTemplate) -> None:
    canvas.saveState()
    if doc.page > 1:
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(LEFT, PAGE_H - 11 * mm, PAGE_W - RIGHT, PAGE_H - 11 * mm)
        canvas.setFont(FONT, 7.2)
        canvas.setFillColor(MUTED)
        canvas.drawString(LEFT, PAGE_H - 8.7 * mm, "DOT - Technical Reference and User Manual")
        canvas.drawRightString(PAGE_W - RIGHT, PAGE_H - 8.7 * mm, "Software 1.0.0")
        canvas.line(LEFT, 11 * mm, PAGE_W - RIGHT, 11 * mm)
        canvas.drawString(LEFT, 7.2 * mm, "Mattia Elisei - MIT License")
        canvas.drawRightString(PAGE_W - RIGHT, 7.2 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _inline(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", escaped)
    escaped = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<link href="\2" color="#2f75b5"><u>\1</u></link>',
        escaped,
    )
    return escaped.replace("  ", " ")


def _heading(text: str, level: int) -> Paragraph:
    style_name = {2: "h2", 3: "h3", 4: "h4"}[level]
    paragraph = Paragraph(_inline(text), STYLES[style_name])
    paragraph._toc_level = level - 2  # type: ignore[attr-defined]
    return paragraph


def _image(path_text: str, caption: str) -> list[Flowable]:
    path = (HERE / path_text).resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    with PILImage.open(path) as source:
        width_px, height_px = source.size
    max_width = CONTENT_W
    max_height = 112 * mm
    scale = min(max_width / width_px, max_height / height_px)
    image = Image(str(path), width=width_px * scale, height=height_px * scale)
    image.hAlign = "CENTER"
    return [image, Paragraph(_inline(caption), STYLES["caption"])]


def _column_widths(rows: list[list[str]]) -> list[float]:
    count = len(rows[0])
    if count == 1:
        return [CONTENT_W]
    lengths = []
    for column in range(count):
        longest = max(len(re.sub(r"[`*]", "", row[column])) for row in rows)
        lengths.append(max(6, min(longest, 45)))
    total = sum(lengths)
    raw = [CONTENT_W * value / total for value in lengths]
    minimum = 22 * mm if count <= 4 else 15 * mm
    adjusted = [max(minimum, value) for value in raw]
    excess = sum(adjusted) - CONTENT_W
    if excess > 0:
        flexible = [max(0.0, value - minimum) for value in adjusted]
        available = sum(flexible)
        if available > 0:
            adjusted = [
                value - excess * flex / available
                for value, flex in zip(adjusted, flexible, strict=True)
            ]
    return adjusted


def _markdown_table(rows: list[list[str]]) -> Table:
    data: list[list[Paragraph]] = []
    for row_index, row in enumerate(rows):
        style = STYLES["table_header"] if row_index == 0 else STYLES["table"]
        data.append([Paragraph(_inline(cell.strip()), style) for cell in row])
    table = Table(data, colWidths=_column_widths(rows), repeatRows=1, hAlign="LEFT")
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.35, RULE),
    ]
    for row_index in range(1, len(rows)):
        if row_index % 2 == 0:
            commands.append(
                ("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#f8fafc"))
            )
    table.setStyle(TableStyle(commands))
    return table


def _callout(text: str) -> Table:
    body = Paragraph(_inline(text), STYLES["callout"])
    table = Table([[body]], colWidths=[CONTENT_W - 5 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BLUE),
                ("BOX", (0, 0), (-1, -1), 0.6, MID_BLUE),
                ("LINEBEFORE", (0, 0), (0, -1), 3.0, BLUE),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _list(items: list[str], ordered: bool) -> Table:
    """Render a page-splittable list without ReportLab's drifting bullets."""

    marker_style = ParagraphStyle(
        "DOTListMarker",
        parent=STYLES["body"],
        textColor=BLUE,
        alignment=TA_CENTER,
    )
    rows = [
        [
            Paragraph(f"{index}." if ordered else "&#8226;", marker_style),
            Paragraph(_inline(item), STYLES["body"]),
        ]
        for index, item in enumerate(items, start=1)
    ]
    table = Table(
        rows,
        colWidths=[7 * mm, CONTENT_W - 7 * mm],
        hAlign="LEFT",
        splitByRow=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (0, -1), 2),
                ("RIGHTPADDING", (1, 0), (1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    table.spaceAfter = 5
    return table


def _parse_markdown(text: str) -> list[Flowable]:
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("## Document purpose"))
    lines = lines[start:]
    story: list[Flowable] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            story.append(
                Paragraph(_inline(" ".join(item.strip() for item in paragraph)), STYLES["body"])
            )
            paragraph.clear()

    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            index += 1
            continue
        if stripped == "<!-- pagebreak -->":
            flush_paragraph()
            story.append(PageBreak())
            index += 1
            continue
        if stripped.startswith("```"):
            flush_paragraph()
            code: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code.append(lines[index].rstrip())
                index += 1
            pre = Preformatted(
                "\n".join(code),
                ParagraphStyle(
                    "Code", fontName="Courier", fontSize=6.6, leading=8.2, textColor=TEXT
                ),
            )
            wrapper = Table([[pre]], colWidths=[CONTENT_W - 4 * mm])
            wrapper.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), CODE_BG),
                        ("BOX", (0, 0), (-1, -1), 0.4, RULE),
                        ("LEFTPADDING", (0, 0), (-1, -1), 7),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            story.extend([wrapper, Spacer(1, 5)])
            index += 1
            continue
        heading_match = re.match(r"^(#{2,4})\s+(.+)$", stripped)
        if heading_match:
            flush_paragraph()
            story.append(_heading(heading_match.group(2), len(heading_match.group(1))))
            index += 1
            continue
        image_match = re.match(r"^!\[([^]]+)\]\(([^)]+)\)$", stripped)
        if image_match:
            flush_paragraph()
            story.extend(_image(image_match.group(2), image_match.group(1)))
            index += 1
            continue
        if stripped.startswith("> "):
            flush_paragraph()
            story.extend([_callout(stripped[2:]), Spacer(1, 5)])
            index += 1
            continue
        if (
            stripped.startswith("|")
            and index + 1 < len(lines)
            and re.match(r"^\s*\|(?:\s*:?-+:?\s*\|)+\s*$", lines[index + 1])
        ):
            flush_paragraph()
            rows: list[list[str]] = []
            rows.append([cell.strip() for cell in stripped.strip("|").split("|")])
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append([cell.strip() for cell in lines[index].strip().strip("|").split("|")])
                index += 1
            story.extend([_markdown_table(rows), Spacer(1, 7)])
            continue
        if re.match(r"^-\s+", stripped):
            flush_paragraph()
            items: list[str] = []
            while index < len(lines) and re.match(r"^\s*-\s+", lines[index]):
                items.append(re.sub(r"^\s*-\s+", "", lines[index]).strip())
                index += 1
            story.append(_list(items, ordered=False))
            continue
        if re.match(r"^\d+\.\s+", stripped):
            flush_paragraph()
            items = []
            while index < len(lines) and re.match(r"^\s*\d+\.\s+", lines[index]):
                items.append(re.sub(r"^\s*\d+\.\s+", "", lines[index]).strip())
                index += 1
            story.append(_list(items, ordered=True))
            continue
        paragraph.append(stripped)
        index += 1
    flush_paragraph()
    return story


def _cover() -> list[Flowable]:
    title_style = ParagraphStyle(
        "CoverTitle",
        fontName=FONT_BOLD,
        fontSize=29,
        leading=34,
        textColor=NAVY,
        alignment=TA_LEFT,
        spaceAfter=8,
    )
    subtitle_style = ParagraphStyle(
        "CoverSubtitle",
        fontName=FONT,
        fontSize=16,
        leading=21,
        textColor=BLUE,
        alignment=TA_LEFT,
    )
    meta_style = ParagraphStyle(
        "CoverMeta",
        fontName=FONT,
        fontSize=9.6,
        leading=14,
        textColor=TEXT,
    )
    story: list[Flowable] = [
        Spacer(1, 18 * mm),
        Paragraph("DOT", title_style),
        Paragraph("Dipole Optimization Tool", subtitle_style),
        Spacer(1, 5 * mm),
        Table(
            [["Technical Reference", "User Manual"]],
            colWidths=[62 * mm, 62 * mm],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, 0), NAVY),
                    ("BACKGROUND", (1, 0), (1, 0), BLUE),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                    ("FONTNAME", (0, 0), (-1, -1), FONT_BOLD),
                    ("FONTSIZE", (0, 0), (-1, -1), 12),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ]
            ),
        ),
        Spacer(1, 15 * mm),
        Paragraph(
            "A source-accurate disclosure of DOT's geometry, electromagnetic kernel, conductor model, constrained NSGA-II search, final verification, outputs, and operating workflow.",
            ParagraphStyle(
                "CoverLead",
                parent=STYLES["body"],
                fontSize=12,
                leading=17,
                textColor=TEXT,
                spaceAfter=16,
            ),
        ),
        Spacer(1, 15 * mm),
        Table(
            [
                ["Software", "DOT 1.0.0"],
                ["Source state", "DOT 1.0.0 source"],
                ["Manual", "Edition 1.1 - 29 July 2026"],
                ["Author", "Mattia Elisei"],
                ["Affiliations", "INFN Milan and University of Rome La Sapienza"],
                ["License", "MIT"],
            ],
            colWidths=[34 * mm, 116 * mm],
            style=TableStyle(
                [
                    ("FONTNAME", (0, 0), (0, -1), FONT_BOLD),
                    ("FONTNAME", (1, 0), (1, -1), FONT),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("TEXTCOLOR", (0, 0), (-1, -1), TEXT),
                    ("BACKGROUND", (0, 0), (0, -1), LIGHT_BLUE),
                    ("GRID", (0, 0), (-1, -1), 0.35, RULE),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            ),
        ),
        Spacer(1, 13 * mm),
        Paragraph("Two-dimensional coil-only superconducting dipole target synthesis", meta_style),
        PageBreak(),
    ]
    return story


def _front_matter(source_text: str) -> list[Flowable]:
    status_match = re.search(r"^> Independent review status: (.+)$", source_text, re.MULTILINE)
    status = status_match.group(1) if status_match else "not recorded"
    story: list[Flowable] = [
        Paragraph("Document control and interpretation", STYLES["h2"]),
        Paragraph(
            "This manual documents one identified software snapshot. Once that snapshot is committed, retain the exact commit identifier with the campaign evidence. If the source changes, verify every equation, default, workflow statement, and screenshot-equivalent diagram before reusing the manual as an authoritative reference.",
            STYLES["body"],
        ),
        _markdown_table(
            [
                ["Control item", "Recorded value"],
                ["Software release", "DOT 1.0.0"],
                ["Source state", "DOT 1.0.0 source, 29 July 2026"],
                ["Manual version", "1.1"],
                ["Independent review", status],
                ["Model boundary", "2D, infinitely long, coil-only, no iron"],
            ]
        ),
        Spacer(1, 6),
        _callout(
            "A certified result means that the decoded straight-block air-core cross-section satisfies the declared DOT equations and constraints during final verification. It is not a construction drawing or a complete magnet sign-off."
        ),
        Spacer(1, 9),
        *_image("assets/workflow.png", "Figure 1. Complete calculation and evidence path."),
        PageBreak(),
        Paragraph("Contents", STYLES["toc_title"]),
    ]
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle(
            "TOC0",
            fontName=FONT_BOLD,
            fontSize=9.3,
            leading=13,
            textColor=NAVY,
            leftIndent=0,
            firstLineIndent=0,
            spaceBefore=2,
        ),
        ParagraphStyle(
            "TOC1",
            fontName=FONT,
            fontSize=8.4,
            leading=11,
            textColor=TEXT,
            leftIndent=12,
            firstLineIndent=0,
        ),
        ParagraphStyle(
            "TOC2",
            fontName=FONT,
            fontSize=7.7,
            leading=10,
            textColor=MUTED,
            leftIndent=24,
            firstLineIndent=0,
        ),
    ]
    story.extend([toc, PageBreak()])
    return story


def build() -> Path:
    source_text = SOURCE.read_text(encoding="utf-8")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    story = _cover() + _front_matter(source_text) + _parse_markdown(source_text)
    doc = ManualDocTemplate(str(OUTPUT))
    doc.multiBuild(story)
    return OUTPUT


if __name__ == "__main__":
    print(build())
