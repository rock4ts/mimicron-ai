from uuid import UUID

from fastapi import APIRouter

from app.api.dependencies import ConversationServiceDependency
from app.schemas.conversation import ConversationRead

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get(
    "/{conversation_id}",
    response_model=ConversationRead,
    responses={404: {"description": "Диалог не найден"}},
    summary="Получить диалог",
    description="Возвращает метаданные диалога по UUID.",
)
async def get_conversation(
    conversation_id: UUID,
    conversation_service: ConversationServiceDependency,
) -> ConversationRead:
    conversation = await conversation_service.get(conversation_id)
    return ConversationRead.model_validate(conversation)
