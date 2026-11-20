from docx.document import Document as DocumentObject
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree


def _comment_reference_run(comment_id: int) -> etree._Element:
    run = OxmlElement("w:r")
    run_properties = OxmlElement("w:rPr")
    style = OxmlElement("w:rStyle")
    style.set(qn("w:val"), "CommentReference")
    run_properties.append(style)
    run.append(run_properties)
    run.append(OxmlElement("w:commentReference", attrs={qn("w:id"): str(comment_id)}))
    return run


def anchor_comment(
    document: DocumentObject,
    first_element: etree._Element,
    last_element: etree._Element,
    text: str,
    author: str,
    initials: str,
) -> int:
    # Markers sit outside w:ins/w:del; inside them the anchor vanishes on reject.
    comment = document.comments.add_comment(text=text, author=author, initials=initials)
    comment_id = comment.comment_id
    first_element.addprevious(
        OxmlElement("w:commentRangeStart", attrs={qn("w:id"): str(comment_id)})
    )
    range_end = OxmlElement("w:commentRangeEnd", attrs={qn("w:id"): str(comment_id)})
    last_element.addnext(range_end)
    range_end.addnext(_comment_reference_run(comment_id))
    return comment_id
