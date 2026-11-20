import logging
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path

import pymupdf

from redline_kit.core.matching import find_match
from redline_kit.core.models import Edit, EditOutcome, RedlineResult

LOGGER = logging.getLogger(__name__)

DEFAULT_AUTHOR = "redline-kit"
STRIKE_COLOR = (0.85, 0.0, 0.0)
NOTE_COLOR = (1.0, 0.85, 0.2)
REDLINE_SUBJECT = "redline-kit"
REPLACE_PREFIX = "Replace with: "
COMMENT_PREFIX = "Comment: "
DELETE_NOTE = "Delete."


@dataclass
class CharBox:
    page_index: int
    rect: pymupdf.Rect
    text: str
    line_key: tuple[int, int]


def _page_lines(page: pymupdf.Page):
    raw = page.get_text("rawdict", sort=True)
    for block in raw["blocks"]:
        for line_index, line in enumerate(block.get("lines", [])):
            characters = [character for span in line["spans"] for character in span["chars"]]
            if characters:
                yield (block["number"], line_index), characters


def collect_characters(document: pymupdf.Document) -> tuple[str, list[CharBox | None]]:
    characters: list[CharBox | None] = []
    for page in document:
        for line_key, line_characters in _page_lines(page):
            if characters:
                characters.append(None)
            for character in line_characters:
                characters.append(
                    CharBox(page.number, pymupdf.Rect(character["bbox"]), character["c"], line_key)
                )
    return "".join(" " if box is None else box.text for box in characters), characters


def words_under(page: pymupdf.Page, rects: list[pymupdf.Rect]) -> str:
    selected = []
    for _line_key, line_characters in _page_lines(page):
        for character in line_characters:
            box = pymupdf.Rect(character["bbox"])
            center = pymupdf.Point((box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2)
            if any(rect.contains(center) for rect in rects):
                selected.append(character["c"])
        selected.append(" ")
    return " ".join("".join(selected).split())


def note_text(edit: Edit) -> str:
    lines = [f"{REPLACE_PREFIX}{edit.replace}" if edit.replace else DELETE_NOTE]
    if edit.comment:
        lines.append(f"{COMMENT_PREFIX}{edit.comment}")
    return "\n".join(lines)


def parse_note(content: str) -> tuple[str | None, str | None]:
    replacement = None
    comments = []
    for line in content.splitlines():
        if line.startswith(REPLACE_PREFIX):
            replacement = line[len(REPLACE_PREFIX) :]
        elif line.startswith(COMMENT_PREFIX):
            comments.append(line[len(COMMENT_PREFIX) :])
        elif line.strip() and line.strip() != DELETE_NOTE:
            comments.append(line.strip())
    return replacement, "\n".join(comments) or None


def _line_rects(characters: list[CharBox]) -> dict[int, list[pymupdf.Rect]]:
    rects_by_page: dict[int, list[pymupdf.Rect]] = {}
    for (page_index, _line_key), line_characters in groupby(
        characters, key=lambda character: (character.page_index, character.line_key)
    ):
        rect = pymupdf.Rect()
        for character in line_characters:
            rect |= character.rect
        rects_by_page.setdefault(page_index, []).append(rect)
    return rects_by_page


def _add_note(page: pymupdf.Page, point: pymupdf.Point, content: str, author: str) -> None:
    note = page.add_text_annot(point, content, icon="Comment")
    note.set_info(title=author, subject=REDLINE_SUBJECT)
    note.set_colors(stroke=NOTE_COLOR)
    note.update()


def apply_pdf_edits(
    document: pymupdf.Document, edits: list[Edit], author: str = DEFAULT_AUTHOR
) -> RedlineResult:
    stream_text, characters = collect_characters(document)
    outcomes = []
    for edit in edits:
        match = find_match([stream_text], edit.find, edit.occurrence)
        if match is None:
            LOGGER.warning("Unmatched edit %r: text not found", edit.find)
            first_page = document[0]
            _add_note(
                first_page,
                pymupdf.Point(first_page.rect.width - 40, 24),
                f'Not applied: could not find "{edit.find}".\n{note_text(edit)}',
                author,
            )
            outcomes.append(EditOutcome(edit=edit, status="unmatched", reason="text not found"))
            continue

        hit_characters = [
            box
            for box in characters[match.start : match.end]
            if box is not None and box.text.strip()
        ]
        content = note_text(edit)
        rects_by_page = _line_rects(hit_characters)
        for page_index, rects in rects_by_page.items():
            page = document[page_index]
            strike = page.add_strikeout_annot(quads=[rect.quad for rect in rects])
            strike.set_info(title=author, content=content, subject=REDLINE_SUBJECT)
            strike.set_colors(stroke=STRIKE_COLOR)
            strike.update()
        first_page_index = min(rects_by_page)
        first_rect = rects_by_page[first_page_index][0]
        first_page = document[first_page_index]
        _add_note(
            first_page, pymupdf.Point(first_page.rect.width - 40, first_rect.y0), content, author
        )
        outcomes.append(
            EditOutcome(
                edit=edit,
                status="applied",
                method=match.method,
                score=match.score,
                matched_text=stream_text[match.start : match.end],
                location=", ".join(f"page {index + 1}" for index in rects_by_page),
            )
        )
    return RedlineResult(outcomes=outcomes)


def redline_pdf(
    input_path: Path, edits: list[Edit], output_path: Path, author: str = DEFAULT_AUTHOR
) -> RedlineResult:
    document = pymupdf.open(input_path)
    result = apply_pdf_edits(document, edits, author=author)
    document.save(output_path, garbage=3, deflate=True)
    return result
