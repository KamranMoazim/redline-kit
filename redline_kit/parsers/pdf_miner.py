from dataclasses import dataclass
from pathlib import Path

import pymupdf

from redline_kit.core.models import MinedEdit
from redline_kit.writers.pdf_redline import parse_note, words_under

HORIZONTAL_TOLERANCE = 1.0
MIN_LINE_COVERAGE = 0.6


@dataclass
class ColoredSpan:
    rect: pymupdf.Rect
    text: str
    baseline: float
    size: float
    line_key: tuple[int, int]


@dataclass
class FlattenedMark:
    kind: str
    text: str
    rect: pymupdf.Rect
    line_key: tuple[int, int]


def _annotation_rects(annotation: pymupdf.Annot) -> list[pymupdf.Rect]:
    vertices = annotation.vertices or []
    if len(vertices) < 4:
        return [annotation.rect]
    return [
        pymupdf.Quad(vertices[index : index + 4]).rect for index in range(0, len(vertices) - 3, 4)
    ]


def mine_annotations(page: pymupdf.Page) -> list[MinedEdit]:
    mined = []
    markup_contents = set()
    annotations = list(page.annots() or [])
    for annotation in annotations:
        kind = annotation.type[1]
        info = annotation.info
        if kind not in ("StrikeOut", "Underline"):
            continue
        content = info.get("content", "")
        markup_contents.add(content)
        replacement, comment = parse_note(content)
        marked_text = words_under(page, _annotation_rects(annotation))
        is_strike = kind == "StrikeOut"
        mined.append(
            MinedEdit(
                source="annotation",
                kind=("replacement" if replacement else "deletion") if is_strike else "insertion",
                find=marked_text if is_strike else None,
                replace=replacement if is_strike else marked_text,
                comment=comment,
                author=info.get("title") or None,
                page=page.number + 1,
            )
        )
    for annotation in annotations:
        content = annotation.info.get("content", "")
        if (
            annotation.type[1] in ("Text", "FreeText")
            and content
            and content not in markup_contents
        ):
            mined.append(
                MinedEdit(
                    source="annotation",
                    kind="comment",
                    comment=content,
                    author=annotation.info.get("title") or None,
                    page=page.number + 1,
                )
            )
    return mined


def _is_colored(color: int) -> bool:
    red, green, blue = (color >> 16) & 255, (color >> 8) & 255, color & 255
    return max(red, green, blue) - min(red, green, blue) > 60


def _horizontal_segments(page: pymupdf.Page) -> list[tuple[float, float, float]]:
    segments = []
    for drawing in page.get_drawings():
        for item in drawing["items"]:
            if item[0] == "l" and abs(item[1].y - item[2].y) <= HORIZONTAL_TOLERANCE:
                start_x, end_x = sorted((item[1].x, item[2].x))
                segments.append((start_x, end_x, (item[1].y + item[2].y) / 2))
            elif item[0] == "re" and item[1].height <= 2 * HORIZONTAL_TOLERANCE:
                segments.append((item[1].x0, item[1].x1, (item[1].y0 + item[1].y1) / 2))
    return segments


def _colored_spans(page: pymupdf.Page) -> list[ColoredSpan]:
    link_rects = [link["from"] for link in page.get_links()]
    spans = []
    for block in page.get_text("dict")["blocks"]:
        for line_index, line in enumerate(block.get("lines", [])):
            for span in line["spans"]:
                rect = pymupdf.Rect(span["bbox"])
                if not span["text"].strip() or not _is_colored(span["color"]):
                    continue
                if any(rect.intersects(link_rect) for link_rect in link_rects):
                    continue
                spans.append(
                    ColoredSpan(
                        rect,
                        span["text"],
                        span["origin"][1],
                        span["size"],
                        (block["number"], line_index),
                    )
                )
    return spans


def _classify(span: ColoredSpan, segments: list[tuple[float, float, float]]) -> str | None:
    for start_x, end_x, line_y in segments:
        overlap = min(end_x, span.rect.x1) - max(start_x, span.rect.x0)
        if overlap < MIN_LINE_COVERAGE * span.rect.width:
            continue
        if span.baseline - 0.6 * span.size <= line_y <= span.baseline - 0.1 * span.size:
            return "deletion"
        if span.baseline - 0.1 * span.size < line_y <= span.baseline + 0.3 * span.size:
            return "insertion"
    return None


def mine_flattened(page: pymupdf.Page) -> list[MinedEdit]:
    segments = _horizontal_segments(page)
    marks: list[FlattenedMark] = []
    for span in _colored_spans(page):
        kind = _classify(span, segments)
        if kind is None:
            continue
        previous = marks[-1] if marks else None
        if previous and previous.kind == kind and previous.line_key == span.line_key:
            previous.text += span.text
            previous.rect |= span.rect
            continue
        marks.append(FlattenedMark(kind, span.text, pymupdf.Rect(span.rect), span.line_key))

    mined: list[MinedEdit] = []
    index = 0
    while index < len(marks):
        mark = marks[index]
        following = marks[index + 1] if index + 1 < len(marks) else None
        if mark.kind == "deletion" and following is not None and following.kind == "insertion":
            mined.append(
                MinedEdit(
                    source="flattened",
                    kind="replacement",
                    find=mark.text.strip(),
                    replace=following.text.strip(),
                    page=page.number + 1,
                    confidence="probable",
                )
            )
            index += 2
            continue
        is_deletion = mark.kind == "deletion"
        mined.append(
            MinedEdit(
                source="flattened",
                kind=mark.kind,
                find=mark.text.strip() if is_deletion else None,
                replace=None if is_deletion else mark.text.strip(),
                page=page.number + 1,
                confidence="probable",
            )
        )
        index += 1
    return mined


def mine_pdf_document(document: pymupdf.Document) -> list[MinedEdit]:
    mined = []
    for page in document:
        mined.extend(mine_annotations(page))
        mined.extend(mine_flattened(page))
    return mined


def mine_pdf(path: Path) -> list[MinedEdit]:
    with pymupdf.open(path) as document:
        return mine_pdf_document(document)
