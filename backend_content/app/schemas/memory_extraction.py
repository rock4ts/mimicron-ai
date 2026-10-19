from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.memory import MemoryType
from app.schemas.companion import strip_non_empty
from app.schemas.memory import MemoryCreate


class MemoryCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: MemoryType
    content: str = Field(min_length=1)
    importance: Decimal = Field(ge=0, le=1)
    confidence: Decimal = Field(ge=0, le=1)

    _strip_content = field_validator("content")(strip_non_empty)

    def to_memory_create(self) -> MemoryCreate:
        return MemoryCreate(
            type=self.type,
            content=self.content,
            importance=self.importance,
            confidence=self.confidence,
        )


class MemoryExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memories: list[MemoryCandidate]
