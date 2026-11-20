import copy
from collections.abc import Iterator
from dataclasses import dataclass

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

SPECIAL_CHARACTERS = {"tab": "\t", "br": "\n", "cr": "\n", "noBreakHyphen": "-"}
HIDDEN_RUN_CONTAINERS = {"del", "moveFrom"}
NORMALIZED_CHARACTERS = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "′": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "″": '"',
        " ": " ",
        " ": " ",
        " ": " ",
        "–": "-",
        "—": "-",
    }
)


def w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def local_name(element: etree._Element) -> str:
    return etree.QName(element).localname if isinstance(element.tag, str) else ""


@dataclass
class RunSlice:
    run: etree._Element
    start: int
    end: int


@dataclass
class ParagraphTextMap:
    paragraph: etree._Element
    text: str
    slices: list[RunSlice]


def child_length(child: etree._Element) -> int:
    name = local_name(child)
    if name == "t":
        return len(child.text or "")
    return 1 if name in SPECIAL_CHARACTERS else 0


def run_text(run: etree._Element) -> str:
    parts = []
    for child in run:
        name = local_name(child)
        if name == "t":
            parts.append(child.text or "")
        elif name in SPECIAL_CHARACTERS:
            parts.append(SPECIAL_CHARACTERS[name])
    return "".join(parts)


def is_visible_run(run: etree._Element, paragraph: etree._Element) -> bool:
    ancestor = run.getparent()
    while ancestor is not None and ancestor is not paragraph:
        name = local_name(ancestor)
        if name in HIDDEN_RUN_CONTAINERS or name == "p":
            return False
        ancestor = ancestor.getparent()
    return ancestor is paragraph


def iter_paragraphs(body: etree._Element) -> Iterator[etree._Element]:
    for paragraph in body.iter(w("p")):
        if not any(local_name(ancestor) == "txbxContent" for ancestor in paragraph.iterancestors()):
            yield paragraph


def build_text_map(paragraph: etree._Element) -> ParagraphTextMap:
    slices = []
    parts = []
    offset = 0
    for run in paragraph.iter(w("r")):
        if not is_visible_run(run, paragraph):
            continue
        text = run_text(run)
        slices.append(RunSlice(run=run, start=offset, end=offset + len(text)))
        parts.append(text)
        offset += len(text)
    return ParagraphTextMap(paragraph=paragraph, text="".join(parts), slices=slices)


def split_run(run: etree._Element, offset: int) -> etree._Element:
    """Split `run` at `offset`; `run` keeps the left part, the new right run is returned."""
    right_run = copy.deepcopy(run)
    run.addnext(right_run)
    _keep_range(run, 0, offset)
    _keep_range(right_run, offset, None)
    return right_run


def _keep_range(run: etree._Element, keep_start: int, keep_end: int | None) -> None:
    position = 0
    for child in list(run):
        if local_name(child) == "rPr":
            continue
        length = child_length(child)
        child_start, child_end = position, position + length
        position = child_end
        upper = child_end if keep_end is None else min(child_end, keep_end)
        lower = max(child_start, keep_start)
        if length == 0:
            in_range = child_start >= keep_start and (keep_end is None or child_start < keep_end)
            if not in_range:
                run.remove(child)
        elif upper <= lower:
            run.remove(child)
        elif local_name(child) == "t" and (lower > child_start or upper < child_end):
            child.text = child.text[lower - child_start : upper - child_start]
            child.set(XML_SPACE, "preserve")


def normalize(text: str) -> tuple[str, list[int]]:
    """Return normalized text and a map from each normalized index to the original index."""
    translated = text.translate(NORMALIZED_CHARACTERS)
    characters = []
    index_map = []
    previous_was_space = False
    for index, character in enumerate(translated):
        if character.isspace():
            if previous_was_space:
                continue
            character = " "
            previous_was_space = True
        else:
            previous_was_space = False
        characters.append(character)
        index_map.append(index)
    return "".join(characters), index_map


def normalize_needle(text: str) -> str:
    return normalize(text)[0].strip()
