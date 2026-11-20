import copy
import json
from pathlib import Path

import docx
import pytest
from lxml import etree

from redline_kit.core.models import Edit
from redline_kit.core.textmap import iter_paragraphs, local_name, w

FIXTURES_DIR = Path(__file__).parent / "fixtures"
EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
CONTRACT_DOCX = FIXTURES_DIR / "contract.docx"
CONTRACT_PDF = FIXTURES_DIR / "contract.pdf"
FLATTENED_PDF = FIXTURES_DIR / "flattened_redline.pdf"

EXACT_EDITS = [
    Edit(
        clause_ref="2",
        find="within thirty (30) days",
        replace="within forty-five (45) days",
        comment="Align with owner terms.",
    ),
    Edit(
        find="The Contractor may terminate", replace="Either party may terminate", comment="Mutual."
    ),
    Edit(find="within thirty (30) days", occurrence=3, replace="within sixty (60) days"),
    Edit(clause_ref="6", find="from all claims arising out of the Work"),
    Edit(clause_ref="8", find="State of Texas", replace="State of New York"),
]


@pytest.fixture
def contract():
    return docx.Document(str(CONTRACT_DOCX))


@pytest.fixture
def example_edits() -> list[Edit]:
    return [Edit(**item) for item in json.loads((EXAMPLES_DIR / "edits.json").read_text())]


def _resolve(body: etree._Element, keep: str) -> etree._Element:
    resolved = copy.deepcopy(body)
    drop = "ins" if keep == "del" else "del"
    for element in list(resolved.iter(w(drop))):
        element.getparent().remove(element)
    for element in list(resolved.iter(w(keep))):
        parent = element.getparent()
        index = parent.index(element)
        for offset, child in enumerate(list(element)):
            parent.insert(index + offset, child)
        parent.remove(element)
    for element in resolved.iter(w("delText")):
        element.tag = w("t")
    return resolved


def document_text(body: etree._Element) -> list[str]:
    return [
        "".join(text.text or "" for text in paragraph.iter(w("t")))
        for paragraph in iter_paragraphs(body)
    ]


def accept_all(body: etree._Element) -> list[str]:
    return document_text(_resolve(body, "ins"))


def reject_all(body: etree._Element) -> list[str]:
    return document_text(_resolve(body, "del"))


def revisions(body: etree._Element) -> list[etree._Element]:
    return [element for element in body.iter() if local_name(element) in ("ins", "del")]
