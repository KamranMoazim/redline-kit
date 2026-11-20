from typing import Literal

from pydantic import BaseModel, Field


class Edit(BaseModel):
    clause_ref: str | None = None
    find: str = Field(min_length=1)
    replace: str | None = None
    comment: str | None = None
    occurrence: int = Field(default=1, ge=1)


class EditOutcome(BaseModel):
    edit: Edit
    status: Literal["applied", "unmatched"]
    method: Literal["exact", "fuzzy"] | None = None
    score: float | None = None
    matched_text: str | None = None
    location: str | None = None
    reason: str | None = None


class RedlineResult(BaseModel):
    outcomes: list[EditOutcome] = []

    @property
    def applied(self) -> list[EditOutcome]:
        return [outcome for outcome in self.outcomes if outcome.status == "applied"]

    @property
    def unmatched(self) -> list[EditOutcome]:
        return [outcome for outcome in self.outcomes if outcome.status == "unmatched"]


class MinedEdit(BaseModel):
    source: Literal["track_changes", "comment", "annotation", "flattened"]
    kind: Literal["replacement", "deletion", "insertion", "comment"]
    clause_ref: str | None = None
    find: str | None = None
    replace: str | None = None
    comment: str | None = None
    author: str | None = None
    page: int | None = None
    confidence: Literal["high", "probable"] = "high"
