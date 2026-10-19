from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.memory import MemoryType
from app.schemas.companion import strip_non_empty, strip_optional_non_empty


class MemoryCreate(BaseModel):
    type: MemoryType
    content: str = Field(min_length=1)
    importance: Decimal = Field(ge=0, le=1)
    confidence: Decimal = Field(ge=0, le=1)

    _strip_content = field_validator("content")(strip_non_empty)


class MemoryUpdate(BaseModel):
    type: MemoryType | None = None
    content: str | None = Field(default=None, min_length=1)
    importance: Decimal | None = Field(default=None, ge=0, le=1)
    confidence: Decimal | None = Field(default=None, ge=0, le=1)

    _strip_content = field_validator("content")(strip_optional_non_empty)

    @model_validator(mode="after")
    def require_update(self) -> "MemoryUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("fields cannot be null")
        return self
