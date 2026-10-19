from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def strip_non_empty(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("must not be empty")
    return stripped


def strip_optional_non_empty(value: str | None) -> str | None:
    return strip_non_empty(value) if value is not None else None


class CompanionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    personality: str = Field(min_length=1, max_length=10_000)

    _strip_name = field_validator("name")(strip_non_empty)
    _strip_personality = field_validator("personality")(strip_non_empty)


class CompanionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    personality: str | None = Field(default=None, min_length=1, max_length=10_000)

    _strip_values = field_validator("name", "personality")(strip_optional_non_empty)

    @model_validator(mode="after")
    def require_update(self) -> "CompanionUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("fields cannot be null")
        return self


class CompanionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    personality: str
    created_at: datetime
    updated_at: datetime
