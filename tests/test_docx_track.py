import io
import zipfile

import docx
from lxml import etree

from redline_kit.core.models import Edit
from redline_kit.core.textmap import w
from redline_kit.writers.docx_track import apply_docx_edits
from tests.conftest import EXACT_EDITS, accept_all, document_text, reject_all, revisions


def _saved_document_xml(document) -> etree._Element:
    buffer = io.BytesIO()
    document.save(buffer)
    with zipfile.ZipFile(buffer) as archive:
        return etree.fromstring(archive.read("word/document.xml"))


def test_accept_and_reject_all(contract):
    original = document_text(contract.element.body)
    result = apply_docx_edits(contract, EXACT_EDITS)
    assert len(result.applied) == len(EXACT_EDITS)

    body = contract.element.body
    assert reject_all(body) == original
    accepted = "\n".join(accept_all(body))
    assert "pay Subcontractor within forty-five (45) days after receipt" in accepted
    assert "Either party may terminate this Agreement" in accepted
    assert "claim for additional cost within sixty (60) days" in accepted
    assert "Released within thirty (30) days" in accepted
    assert "arising out of the Work" not in accepted
    assert "laws of the State of New York." in accepted


def test_formatting_and_numbering_kept(contract):
    paragraph_properties_before = [
        etree.tostring(paragraph._p.pPr) if paragraph._p.pPr is not None else None
        for paragraph in contract.paragraphs
    ]
    apply_docx_edits(contract, EXACT_EDITS)
    paragraph_properties_after = [
        etree.tostring(paragraph._p.pPr) if paragraph._p.pPr is not None else None
        for paragraph in contract.paragraphs
    ]
    assert paragraph_properties_after == paragraph_properties_before

    deleted_runs = contract.element.body.findall(f".//{w('del')}/{w('r')}")
    contractor_run = next(run for run in deleted_runs if run.findtext(w("delText")) == "Contractor")
    assert contractor_run.find(f"{w('rPr')}/{w('b')}") is not None


def test_xml_is_valid_with_unique_revision_ids(contract):
    apply_docx_edits(contract, EXACT_EDITS)
    document_xml = _saved_document_xml(contract)
    revision_elements = revisions(document_xml)
    ids = [element.get(w("id")) for element in revision_elements]
    assert len(ids) == len(set(ids)) > 0
    assert all(element.get(w("author")) and element.get(w("date")) for element in revision_elements)
    assert not document_xml.findall(f".//{w('del')}//{w('t')}")
    assert not document_xml.findall(f".//{w('ins')}//{w('delText')}")


def test_revision_ids_start_above_existing_ids(contract):
    apply_docx_edits(contract, [Edit(find="State of Texas", replace="State of Ohio")])
    bookmark_id = int(contract.element.body.find(f".//{w('bookmarkStart')}").get(w("id")))
    assert all(
        int(element.get(w("id"))) > bookmark_id for element in revisions(contract.element.body)
    )


def test_unmatched_edit_becomes_comment_without_touching_text(contract):
    original = document_text(contract.element.body)
    result = apply_docx_edits(contract, [Edit(find="liquidated damages", comment="Add a cap.")])
    assert result.unmatched[0].reason == "text not found"
    assert not revisions(contract.element.body)
    assert document_text(contract.element.body) == original
    assert "Add a cap." in next(iter(contract.comments)).text


def test_overlapping_edit_is_reported_not_applied(contract):
    result = apply_docx_edits(
        contract,
        [
            Edit(find="State of Texas", replace="State of Ohio"),
            Edit(find="of Texas", replace="of Utah"),
        ],
    )
    assert [outcome.status for outcome in result.outcomes] == ["applied", "unmatched"]
    assert result.outcomes[1].reason == "overlaps another edit"


def test_output_reopens_with_python_docx(contract, tmp_path):
    apply_docx_edits(contract, EXACT_EDITS)
    path = tmp_path / "out.docx"
    contract.save(str(path))
    assert len(docx.Document(str(path)).paragraphs) == len(contract.paragraphs)
