import copy
import logging
from datetime import UTC, datetime
from pathlib import Path

import docx
from docx.document import Document as DocumentObject
from docx.oxml import OxmlElement
from lxml import etree

from redline_kit.core.clauses import assign_clause_refs
from redline_kit.core.matching import Match, find_match
from redline_kit.core.models import Edit, EditOutcome, RedlineResult
from redline_kit.core.textmap import (
    XML_SPACE,
    ParagraphTextMap,
    build_text_map,
    iter_paragraphs,
    local_name,
    split_run,
    w,
)
from redline_kit.writers.docx_comments import anchor_comment

LOGGER = logging.getLogger(__name__)

DEFAULT_AUTHOR = "redline-kit"
WRAPPABLE_TAGS = {
    "r",
    "bookmarkStart",
    "bookmarkEnd",
    "proofErr",
    "commentRangeStart",
    "commentRangeEnd",
}


class RevisionIds:
    def __init__(self, document: DocumentObject) -> None:
        existing = [
            int(value)
            for value in document.element.xpath("//@w:id")
            if str(value).lstrip("-").isdigit()
        ]
        self.next_id = max(existing, default=0) + 1

    def take(self) -> str:
        revision_id = self.next_id
        self.next_id += 1
        return str(revision_id)


def _revision(tag: str, revision_ids: RevisionIds, author: str, date: str) -> etree._Element:
    element = OxmlElement(f"w:{tag}")
    element.set(w("id"), revision_ids.take())
    element.set(w("author"), author)
    element.set(w("date"), date)
    return element


def _isolate_span(text_map: ParagraphTextMap, start: int, end: int) -> list[etree._Element]:
    runs = []
    for run_slice in text_map.slices:
        if run_slice.end <= start or run_slice.start >= end or run_slice.end == run_slice.start:
            continue
        run = run_slice.run
        if end < run_slice.end:
            split_run(run, end - run_slice.start)
        if start > run_slice.start:
            run = split_run(run, start - run_slice.start)
        runs.append(run)
    return runs


def _sibling_chunks(runs: list[etree._Element]) -> list[list[etree._Element]]:
    chunks: list[list[etree._Element]] = []
    run_ids = {id(run) for run in runs}
    index = 0
    while index < len(runs):
        first = runs[index]
        chunk = [first]
        sibling = first.getnext()
        index += 1
        while index < len(runs) and sibling is not None:
            if sibling is runs[index]:
                chunk.append(sibling)
                index += 1
            elif local_name(sibling) in WRAPPABLE_TAGS and id(sibling) not in run_ids:
                chunk.append(sibling)
            else:
                break
            sibling = sibling.getnext()
        while local_name(chunk[-1]) != "r":
            chunk.pop()
        chunks.append(chunk)
    return chunks


def _mark_deleted(run: etree._Element) -> None:
    for child in run:
        if local_name(child) == "t":
            child.tag = w("delText")
            child.set(XML_SPACE, "preserve")
        elif local_name(child) == "instrText":
            child.tag = w("delInstrText")


def _paragraph_child(element: etree._Element, paragraph: etree._Element) -> etree._Element:
    while element.getparent() is not paragraph:
        element = element.getparent()
    return element


def apply_tracked_change(
    text_map: ParagraphTextMap,
    start: int,
    end: int,
    replacement: str | None,
    revision_ids: RevisionIds,
    author: str,
    date: str,
) -> tuple[etree._Element, etree._Element]:
    runs = _isolate_span(text_map, start, end)
    first_run_properties = runs[0].find(w("rPr"))
    deletions = []
    for chunk in _sibling_chunks(runs):
        deletion = _revision("del", revision_ids, author, date)
        chunk[0].addprevious(deletion)
        for element in chunk:
            deletion.append(element)
            if local_name(element) == "r":
                _mark_deleted(element)
        deletions.append(deletion)

    anchor_first = deletions[0]
    anchor_last = deletions[-1]
    if replacement:
        insertion = _revision("ins", revision_ids, author, date)
        inserted_run = OxmlElement("w:r")
        if first_run_properties is not None:
            inserted_run.append(copy.deepcopy(first_run_properties))
        inserted_text = OxmlElement("w:t")
        inserted_text.text = replacement
        inserted_text.set(XML_SPACE, "preserve")
        inserted_run.append(inserted_text)
        insertion.append(inserted_run)
        _paragraph_child(deletions[-1], text_map.paragraph).addnext(insertion)
        anchor_first = anchor_last = insertion
    return anchor_first, anchor_last


def _comment_text(edit: Edit) -> str:
    return edit.comment or ""


def _unmatched_comment_text(edit: Edit) -> str:
    lines = [f'Not applied: could not find "{edit.find}" (occurrence {edit.occurrence}).']
    if edit.replace:
        lines.append(f'Suggested replacement: "{edit.replace}".')
    if edit.comment:
        lines.append(edit.comment)
    return " ".join(lines)


def _paragraph_content(paragraph: etree._Element) -> list[etree._Element]:
    return [child for child in paragraph if local_name(child) != "pPr"]


def _initials(author: str) -> str:
    return "".join(part[0] for part in author.replace("-", " ").split() if part).upper()[:3]


def apply_docx_edits(
    document: DocumentObject,
    edits: list[Edit],
    author: str = DEFAULT_AUTHOR,
    now: datetime | None = None,
) -> RedlineResult:
    date = (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ")
    initials = _initials(author)
    body = document.element.body
    paragraphs = list(iter_paragraphs(body))
    clause_refs = assign_clause_refs(document, paragraphs)
    original_texts = [build_text_map(paragraph).text for paragraph in paragraphs]
    revision_ids = RevisionIds(document)

    outcomes: list[EditOutcome | None] = [None] * len(edits)
    planned: list[tuple[int, int, Match]] = []
    for edit_index, edit in enumerate(edits):
        candidates = [
            paragraph_index
            for paragraph_index in range(len(paragraphs))
            if edit.clause_ref is None or clause_refs[paragraph_index] == edit.clause_ref
        ]
        match = find_match(
            [original_texts[index] for index in candidates], edit.find, edit.occurrence
        )
        if match is None:
            outcomes[edit_index] = EditOutcome(
                edit=edit, status="unmatched", reason="text not found"
            )
            continue
        paragraph_index = candidates[match.haystack_index]
        planned.append((edit_index, paragraph_index, match))

    planned.sort(key=lambda item: (item[1], item[2].start))
    accepted: list[tuple[int, int, Match]] = []
    for item in planned:
        edit_index, paragraph_index, match = item
        previous = accepted[-1] if accepted else None
        if previous and previous[1] == paragraph_index and previous[2].end > match.start:
            outcomes[edit_index] = EditOutcome(
                edit=edits[edit_index], status="unmatched", reason="overlaps another edit"
            )
            continue
        accepted.append(item)

    for edit_index, paragraph_index, match in sorted(
        accepted, key=lambda item: (item[1], -item[2].start)
    ):
        edit = edits[edit_index]
        paragraph = paragraphs[paragraph_index]
        text_map = build_text_map(paragraph)
        matched_text = original_texts[paragraph_index][match.start : match.end]
        anchor_first, anchor_last = apply_tracked_change(
            text_map, match.start, match.end, edit.replace, revision_ids, author, date
        )
        if edit.comment:
            anchor_comment(
                document, anchor_first, anchor_last, _comment_text(edit), author, initials
            )
        outcomes[edit_index] = EditOutcome(
            edit=edit,
            status="applied",
            method=match.method,
            score=match.score,
            matched_text=matched_text,
            location=f"clause {clause_refs[paragraph_index]}"
            if clause_refs[paragraph_index]
            else f"paragraph {paragraph_index + 1}",
        )

    for edit_index, outcome in enumerate(outcomes):
        if outcome is None or outcome.status != "unmatched":
            continue
        edit = edits[edit_index]
        LOGGER.warning("Unmatched edit %r: %s", edit.find, outcome.reason)
        target = next(
            (
                paragraph
                for paragraph, clause_ref in zip(paragraphs, clause_refs, strict=True)
                if _paragraph_content(paragraph)
                and (edit.clause_ref is None or clause_ref == edit.clause_ref)
            ),
            None,
        )
        if target is None:
            continue
        content = _paragraph_content(target)
        anchor_comment(
            document, content[0], content[-1], _unmatched_comment_text(edit), author, initials
        )

    return RedlineResult(outcomes=[outcome for outcome in outcomes if outcome is not None])


def redline_docx(
    input_path: Path, edits: list[Edit], output_path: Path, author: str = DEFAULT_AUTHOR
) -> RedlineResult:
    document = docx.Document(str(input_path))
    result = apply_docx_edits(document, edits, author=author)
    document.save(str(output_path))
    return result
