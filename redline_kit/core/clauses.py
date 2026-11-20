from docx.document import Document as DocumentObject
from lxml import etree

from redline_kit.core.textmap import w


def _style_numbering_level(document: DocumentObject, style_id: str | None) -> int | None:
    visited = set()
    while style_id and style_id not in visited:
        visited.add(style_id)
        style = document.styles.element.find(f"{w('style')}[@{w('styleId')}='{style_id}']")
        if style is None:
            return None
        num_pr = style.find(f"{w('pPr')}/{w('numPr')}")
        if num_pr is not None:
            level = num_pr.find(w("ilvl"))
            return int(level.get(w("val"))) if level is not None else 0
        based_on = style.find(w("basedOn"))
        style_id = based_on.get(w("val")) if based_on is not None else None
    return None


def numbering_level(document: DocumentObject, paragraph: etree._Element) -> int | None:
    num_pr = paragraph.find(f"{w('pPr')}/{w('numPr')}")
    if num_pr is not None:
        num_id = num_pr.find(w("numId"))
        if num_id is not None and num_id.get(w("val")) == "0":
            return None
        level = num_pr.find(w("ilvl"))
        return int(level.get(w("val"))) if level is not None else 0
    style = paragraph.find(f"{w('pPr')}/{w('pStyle')}")
    return _style_numbering_level(document, style.get(w("val")) if style is not None else None)


def assign_clause_refs(
    document: DocumentObject, paragraphs: list[etree._Element]
) -> list[str | None]:
    counters: list[int] = []
    current: str | None = None
    clause_refs = []
    for paragraph in paragraphs:
        level = numbering_level(document, paragraph)
        if level is not None:
            counters = counters[: level + 1] + [0] * (level + 1 - len(counters))
            counters[level] += 1
            current = ".".join(str(counter) for counter in counters[: level + 1])
        clause_refs.append(current)
    return clause_refs
