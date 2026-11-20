from dataclasses import dataclass, field
from pathlib import Path

import docx
from docx.document import Document as DocumentObject
from lxml import etree

from redline_kit.core.clauses import assign_clause_refs
from redline_kit.core.models import MinedEdit
from redline_kit.core.textmap import iter_paragraphs, local_name, w


@dataclass
class PendingChange:
    clause_ref: str | None
    deleted: list[str] = field(default_factory=list)
    inserted: list[str] = field(default_factory=list)
    author: str | None = None
    comment_ids: set[str] = field(default_factory=set)


def _revision_state(run: etree._Element, paragraph: etree._Element) -> tuple[str, str | None]:
    for ancestor in run.iterancestors():
        if ancestor is paragraph:
            break
        name = local_name(ancestor)
        if name in ("del", "ins"):
            return name, ancestor.get(w("author"))
    return "normal", None


def _run_content(run: etree._Element) -> str:
    return "".join(child.text or "" for child in run if local_name(child) in ("t", "delText"))


def _to_mined(change: PendingChange, comments_by_id: dict[str, tuple[str, str]]) -> MinedEdit:
    deleted = "".join(change.deleted) or None
    inserted = "".join(change.inserted) or None
    if deleted and inserted:
        kind = "replacement"
    elif deleted:
        kind = "deletion"
    else:
        kind = "insertion"
    comment_texts = [
        comments_by_id[comment_id][0] for comment_id in sorted(change.comment_ids, key=int)
    ]
    return MinedEdit(
        source="track_changes",
        kind=kind,
        clause_ref=change.clause_ref,
        find=deleted,
        replace=inserted,
        comment="\n".join(comment_texts) or None,
        author=change.author,
    )


def mine_docx_document(document: DocumentObject) -> list[MinedEdit]:
    comments_by_id = {
        str(comment.comment_id): (comment.text, comment.author) for comment in document.comments
    }
    paragraphs = list(iter_paragraphs(document.element.body))
    clause_refs = assign_clause_refs(document, paragraphs)
    mined: list[MinedEdit] = []
    attached_comment_ids: set[str] = set()
    comment_clause: dict[str, str | None] = {}

    for paragraph, clause_ref in zip(paragraphs, clause_refs, strict=True):
        active_comments: set[str] = set()
        change: PendingChange | None = None
        for element in paragraph.iter():
            name = local_name(element)
            if name == "commentRangeStart":
                comment_id = element.get(w("id"))
                active_comments.add(comment_id)
                comment_clause.setdefault(comment_id, clause_ref)
            elif name == "commentRangeEnd":
                active_comments.discard(element.get(w("id")))
            elif name == "r":
                text = _run_content(element)
                if not text:
                    continue
                state, author = _revision_state(element, paragraph)
                if state == "normal":
                    if change is not None:
                        mined.append(_to_mined(change, comments_by_id))
                        change = None
                    continue
                if change is None:
                    change = PendingChange(clause_ref=clause_ref, author=author)
                (change.deleted if state == "del" else change.inserted).append(text)
                change.comment_ids |= active_comments & comments_by_id.keys()
                attached_comment_ids |= active_comments
        if change is not None:
            mined.append(_to_mined(change, comments_by_id))

    for comment_id, (text, author) in comments_by_id.items():
        if comment_id not in attached_comment_ids:
            mined.append(
                MinedEdit(
                    source="comment",
                    kind="comment",
                    clause_ref=comment_clause.get(comment_id),
                    comment=text,
                    author=author,
                )
            )
    return mined


def mine_docx(path: Path) -> list[MinedEdit]:
    return mine_docx_document(docx.Document(str(path)))
