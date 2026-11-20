import logging
import shutil
import subprocess
import sys
from pathlib import Path

import pymupdf
from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
LOGGER = logging.getLogger("make_fixtures")

INTRO = (
    "This Subcontract Agreement (the “Agreement”) is made on 1 November 2026 between "
    "Acme Builders LLC (“Contractor”) and Riverside Electrical Inc. "
    "(“Subcontractor”)."
)

RETAINAGE_ROWS = [
    ("Milestone", "Retainage"),
    ("Until 50% complete", "10%"),
    ("After 50% complete", "5%"),
    ("Final completion", "Released within thirty (30) days"),
]


def add_clause(document, heading: str, *parts: tuple[str, bool]):
    paragraph = document.add_paragraph(style="List Number")
    heading_run = paragraph.add_run(heading + " ")
    heading_run.bold = True
    for text, is_bold in parts:
        run = paragraph.add_run(text)
        run.bold = is_bold or None
    return paragraph


def add_hyperlink(paragraph, url: str, text: str) -> None:
    relationship_id = paragraph.part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relationship_id)
    run = OxmlElement("w:r")
    run_properties = OxmlElement("w:rPr")
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    run_properties.append(underline)
    run.append(run_properties)
    text_element = OxmlElement("w:t")
    text_element.text = text
    run.append(text_element)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def wrap_with_bookmark_and_proof_error(paragraph) -> None:
    runs = paragraph._p.findall(qn("w:r"))
    bookmark_start = OxmlElement("w:bookmarkStart")
    bookmark_start.set(qn("w:id"), "0")
    bookmark_start.set(qn("w:name"), "GoverningLaw")
    bookmark_end = OxmlElement("w:bookmarkEnd")
    bookmark_end.set(qn("w:id"), "0")
    runs[1].addprevious(bookmark_start)
    runs[-1].addnext(bookmark_end)
    proof_start = OxmlElement("w:proofErr")
    proof_start.set(qn("w:type"), "spellStart")
    proof_end = OxmlElement("w:proofErr")
    proof_end.set(qn("w:type"), "spellEnd")
    runs[2].addprevious(proof_start)
    runs[2].addnext(proof_end)


def build_contract_docx(path: Path) -> None:
    document = Document()
    document.styles["Normal"].font.size = Pt(11)
    document.add_heading("Subcontract Agreement", level=1)
    document.add_paragraph(INTRO)

    add_clause(
        document,
        "Scope of Work.",
        (
            "Subcontractor shall furnish all labor, materials and equipment required for the "
            "electrical work described in Exhibit A.",
            False,
        ),
    )
    add_clause(
        document,
        "Payment.",
        (
            "Contractor shall pay Subcontractor within thirty (30) days after receipt of an "
            "approved invoice.",
            False,
        ),
    )
    add_clause(
        document,
        "Termination.",
        ("The ", False),
        ("Contractor", True),
        (
            " may terminate this Agreement for convenience upon seven (7) days’ written notice.",
            False,
        ),
    )
    add_clause(
        document,
        "Retainage.",
        ("Contractor shall withhold retainage as set out in the schedule below.", False),
    )
    table = document.add_table(rows=len(RETAINAGE_ROWS), cols=2)
    table.style = "Table Grid"
    for row_index, (milestone, retainage) in enumerate(RETAINAGE_ROWS):
        table.cell(row_index, 0).text = milestone
        table.cell(row_index, 1).text = retainage
    add_clause(
        document,
        "Change Orders.",
        (
            "Subcontractor shall submit any claim for additional cost within thirty (30) days of "
            "the event giving rise to the claim.",
            False,
        ),
    )
    add_clause(
        document,
        "Indemnity.",
        (
            "To the fullest extent permitted by law, Subcontractor shall indemnify and hold "
            "harmless Contractor from all claims arising out of the Work.",
            False,
        ),
    )
    notices = add_clause(
        document,
        "Notices.",
        ("Notices shall be sent by email to ", False),
    )
    add_hyperlink(notices, "mailto:notices@acme.example", "notices@acme.example")
    notices.add_run(" and are effective within 2 business days after delivery.")
    governing_law = add_clause(
        document,
        "Governing Law.",
        ("This Agreement is governed by the laws of the State of ", False),
        ("Texas", False),
        (".", False),
    )
    wrap_with_bookmark_and_proof_error(governing_law)
    document.save(path)


def build_flattened_pdf(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page()
    font_size = 11
    cursor_y = 100
    segments = [
        ("Contractor shall pay Subcontractor within ", (0, 0, 0), None),
        ("thirty (30)", (0.8, 0, 0), "strike"),
        (" ", (0, 0, 0), None),
        ("forty-five (45)", (0, 0, 0.8), "underline"),
        (" days after receipt.", (0, 0, 0), None),
    ]
    cursor_x = 72.0
    for text, color, decoration in segments:
        page.insert_text((cursor_x, cursor_y), text, fontsize=font_size, color=color)
        width = pymupdf.get_text_length(text, fontsize=font_size)
        if decoration == "strike":
            line_y = cursor_y - font_size * 0.3
            page.draw_line((cursor_x, line_y), (cursor_x + width, line_y), color=color, width=0.8)
        elif decoration == "underline":
            line_y = cursor_y + 1.5
            page.draw_line((cursor_x, line_y), (cursor_x + width, line_y), color=color, width=0.8)
        cursor_x += width
    document.save(path)


def convert_to_pdf(docx_path: Path) -> None:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice is None:
        LOGGER.warning(
            "LibreOffice not found, skipping %s.pdf (run `make fixtures`)", docx_path.stem
        )
        return
    subprocess.run(
        [
            soffice,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(docx_path.parent),
            str(docx_path),
        ],
        check=True,
        capture_output=True,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    contract_path = FIXTURES_DIR / "contract.docx"
    build_contract_docx(contract_path)
    build_flattened_pdf(FIXTURES_DIR / "flattened_redline.pdf")
    if "--pdf" in sys.argv:
        convert_to_pdf(contract_path)
    LOGGER.info("Fixtures written to %s", FIXTURES_DIR)


if __name__ == "__main__":
    main()
