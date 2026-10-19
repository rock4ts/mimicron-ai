from uuid import UUID

from fastapi import APIRouter, status

from app.api.dependencies import ChatServiceDependency, ConversationServiceDependency
from app.schemas.message import MessageCreate, MessageRead

router = APIRouter(prefix="/conversations", tags=["messages"])


@router.get(
    "/{conversation_id}/messages",
    response_model=list[MessageRead],
    responses={404: {"description": "Диалог не найден"}},
    summary="Получить сообщения",
    description="Возвращает сообщения диалога в хронологическом порядке.",
)
async def list_messages(
    conversation_id: UUID,
    conversation_service: ConversationServiceDependency,
) -> list[MessageRead]:
    messages = await conversation_service.list_messages(conversation_id)
    return [MessageRead.model_validate(item) for item in messages]


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "Диалог не найден"},
        502: {"description": "Ошибка LLM provider"},
    },
    summary="Отправить сообщение",
    description="Сохраняет сообщение, подбирает релевантные воспоминания, "
    "передаёт историю LLM-провайдеру и сохраняет ответ.",
)
async def send_message(
    conversation_id: UUID,
    payload: MessageCreate,
    chat_service: ChatServiceDependency,
) -> MessageRead:
    message = await chat_service.send_message(
        conversation_id,
        payload.content,
    )
    return MessageRead.model_validate(message)
