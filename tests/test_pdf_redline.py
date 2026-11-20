import pymupdf
import pytest

from redline_kit.core.textmap import normalize_needle
from redline_kit.parsers.pdf_miner import mine_pdf_document
from redline_kit.writers.pdf_redline import apply_pdf_edits, words_under
from tests.conftest import CONTRACT_PDF, EXACT_EDITS, FLATTENED_PDF

needs_contract_pdf = pytest.mark.skipif(
    not CONTRACT_PDF.exists(), reason="contract.pdf missing, run `make fixtures`"
)


@needs_contract_pdf
def test_strikeouts_cover_the_edited_text():
    document = pymupdf.open(CONTRACT_PDF)
    result = apply_pdf_edits(document, EXACT_EDITS)
    assert len(result.applied) == len(EXACT_EDITS)

    strikeouts = [
        (page, annotation)
        for page in document
        for annotation in page.annots(types=[pymupdf.PDF_ANNOT_STRIKE_OUT])
    ]
    notes = [
        annotation
        for page in document
        for annotation in page.annots(types=[pymupdf.PDF_ANNOT_TEXT])
    ]
    assert len(strikeouts) >= len(EXACT_EDITS)
    assert len(notes) == len(EXACT_EDITS)
    struck_text = " ".join(
        words_under(
            page,
            [
                pymupdf.Quad(annotation.vertices[index : index + 4]).rect
                for index in range(0, len(annotation.vertices), 4)
            ],
        )
        for page, annotation in strikeouts
    )
    for edit in EXACT_EDITS:
        assert normalize_needle(edit.find) in normalize_needle(struck_text)
    assert all(annotation.info["title"] == "redline-kit" for _page, annotation in strikeouts)


@needs_contract_pdf
def test_unmatched_pdf_edit_adds_one_note():
    from redline_kit.core.models import Edit

    document = pymupdf.open(CONTRACT_PDF)
    result = apply_pdf_edits(document, [Edit(find="liquidated damages", comment="Add a cap.")])
    assert result.unmatched
    notes = list(document[0].annots(types=[pymupdf.PDF_ANNOT_TEXT]))
    assert len(notes) == 1 and "Add a cap." in notes[0].info["content"]


@needs_contract_pdf
def test_pdf_round_trip():
    document = pymupdf.open(CONTRACT_PDF)
    apply_pdf_edits(document, EXACT_EDITS)
    reopened = pymupdf.open("pdf", document.tobytes())
    mined = [item for item in mine_pdf_document(reopened) if item.source == "annotation"]
    mined_keys = sorted((normalize_needle(item.find), item.replace, item.comment) for item in mined)
    expected = sorted(
        (normalize_needle(edit.find), edit.replace, edit.comment) for edit in EXACT_EDITS
    )
    assert mined_keys == expected


def test_flattened_redline_is_detected():
    mined = mine_pdf_document(pymupdf.open(FLATTENED_PDF))
    assert [(item.kind, item.find, item.replace, item.confidence) for item in mined] == [
        ("replacement", "thirty (30)", "forty-five (45)", "probable")
    ]


@needs_contract_pdf
def test_clean_contract_pdf_has_no_flattened_marks():
    assert mine_pdf_document(pymupdf.open(CONTRACT_PDF)) == []
