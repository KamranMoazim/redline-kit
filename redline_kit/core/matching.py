from dataclasses import dataclass
from typing import Literal

from rapidfuzz import fuzz

from redline_kit.core.textmap import normalize, normalize_needle

FUZZY_THRESHOLD = 95.0
FUZZY_MIN_LENGTH = 12


@dataclass
class Match:
    haystack_index: int
    start: int
    end: int
    method: Literal["exact", "fuzzy"]
    score: float


def _to_original_span(index_map: list[int], start: int, end: int) -> tuple[int, int]:
    return index_map[start], index_map[end - 1] + 1


def find_match(
    haystacks: list[str],
    needle: str,
    occurrence: int = 1,
    threshold: float = FUZZY_THRESHOLD,
) -> Match | None:
    normalized_needle = normalize_needle(needle)
    if not normalized_needle:
        return None
    normalized_haystacks = [normalize(haystack) for haystack in haystacks]

    seen = 0
    for haystack_index, (normalized_text, index_map) in enumerate(normalized_haystacks):
        position = normalized_text.find(normalized_needle)
        while position != -1:
            seen += 1
            if seen == occurrence:
                start, end = _to_original_span(
                    index_map, position, position + len(normalized_needle)
                )
                return Match(haystack_index, start, end, "exact", 100.0)
            position = normalized_text.find(normalized_needle, position + len(normalized_needle))

    if seen > 0 or len(normalized_needle) < FUZZY_MIN_LENGTH:
        return None
    best: Match | None = None
    for haystack_index, (normalized_text, index_map) in enumerate(normalized_haystacks):
        if len(normalized_text) < len(normalized_needle) * 0.9:
            continue
        alignment = fuzz.partial_ratio_alignment(
            normalized_needle, normalized_text, score_cutoff=threshold
        )
        if alignment is None or (best is not None and alignment.score <= best.score):
            continue
        dest_start, dest_end = alignment.dest_start, alignment.dest_end
        while dest_start < dest_end and normalized_text[dest_start] == " ":
            dest_start += 1
        while dest_end > dest_start and normalized_text[dest_end - 1] == " ":
            dest_end -= 1
        if dest_end > dest_start:
            start, end = _to_original_span(index_map, dest_start, dest_end)
            best = Match(haystack_index, start, end, "fuzzy", alignment.score)
    return best
