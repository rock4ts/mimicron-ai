from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MemoryRelation(StrEnum):
    DUPLICATE = "duplicate"
    UPDATE = "update"
    CONTRADICTION = "contradiction"
    ADDITIONAL = "additional"
    UNRELATED = "unrelated"
    DISCARD = "discard"


_RELATIONS_REQUIRING_EXISTING = {
    MemoryRelation.DUPLICATE,
    MemoryRelation.UPDATE,
    MemoryRelation.CONTRADICTION,
}


class MemoryReconciliationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_index: int = Field(ge=0)
    relation: MemoryRelation
    existing_memory_id: UUID | None = None

    @model_validator(mode="after")
    def relation_matches_existing_id(self) -> "MemoryReconciliationDecision":
        needs_existing = self.relation in _RELATIONS_REQUIRING_EXISTING
        if needs_existing and self.existing_memory_id is None:
            raise ValueError("existing_memory_id is required for this relation")
        if not needs_existing and self.existing_memory_id is not None:
            raise ValueError("existing_memory_id must be omitted for this relation")
        return self


class MemoryReconciliationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: list[MemoryReconciliationDecision]
