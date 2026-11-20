from redline_kit.core.models import Edit
from redline_kit.core.textmap import local_name, w
from redline_kit.writers.docx_track import apply_docx_edits


def _marker(contract, tag):
    return contract.element.body.find(f".//{w(tag)}")


def test_comment_wraps_insertion_at_paragraph_level(contract):
    apply_docx_edits(
        contract, [Edit(find="State of Texas", replace="State of Ohio", comment="Venue.")]
    )
    start = _marker(contract, "commentRangeStart")
    end = _marker(contract, "commentRangeEnd")
    assert local_name(start.getparent()) == "p"
    assert local_name(start.getnext()) == "ins"
    assert local_name(end.getprevious()) == "ins"
    reference_run = end.getnext()
    assert reference_run.find(w("commentReference")) is not None
    comment = next(iter(contract.comments))
    assert (comment.text, comment.author) == ("Venue.", "redline-kit")


def test_comment_on_pure_deletion_wraps_deletion(contract):
    apply_docx_edits(
        contract, [Edit(find="State of Texas", comment="Why delete?")], author="Jane Reviewer"
    )
    start = _marker(contract, "commentRangeStart")
    assert local_name(start.getnext()) == "del"
    assert next(iter(contract.comments)).initials == "JR"
