from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.message import MessageRole
from app.schemas.companion import strip_non_empty


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)

    _strip_content = field_validator("content")(strip_non_empty)


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    role: MessageRole
    content: str
    created_at: datetime
