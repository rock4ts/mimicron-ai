from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, status

from app.api.dependencies import CompanionServiceDependency, ConversationServiceDependency
from app.schemas.companion import CompanionCreate, CompanionRead, CompanionUpdate
from app.schemas.conversation import ConversationRead

router = APIRouter(prefix="/companions", tags=["companions"])


@router.post(
    "",
    response_model=CompanionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать компаньона",
    description="Создаёт AI-компаньона с именем и описанием личности.",
)
async def create_companion(
    payload: Annotated[CompanionCreate, Body(description="Данные нового компаньона")],
    companion_service: CompanionServiceDependency,
) -> CompanionRead:
    return CompanionRead.model_validate(await companion_service.create(payload))


@router.get(
    "",
    response_model=list[CompanionRead],
    summary="Получить список компаньонов",
    description="Возвращает компаньонов текущего пользователя в порядке создания.",
)
async def list_companions(companion_service: CompanionServiceDependency) -> list[CompanionRead]:
    companions = await companion_service.list()
    return [CompanionRead.model_validate(item) for item in companions]


@router.get(
    "/{companion_id}",
    response_model=CompanionRead,
    responses={404: {"description": "Компаньон не найден"}},
    summary="Получить компаньона",
    description="Возвращает компаньона по UUID.",
)
async def get_companion(
    companion_id: UUID,
    companion_service: CompanionServiceDependency,
) -> CompanionRead:
    return CompanionRead.model_validate(await companion_service.get(companion_id))


@router.patch(
    "/{companion_id}",
    response_model=CompanionRead,
    responses={404: {"description": "Компаньон не найден"}},
    summary="Обновить компаньона",
    description="Частично изменяет имя и/или описание личности компаньона.",
)
async def update_companion(
    companion_id: UUID,
    payload: CompanionUpdate,
    companion_service: CompanionServiceDependency,
) -> CompanionRead:
    companion = await companion_service.update(companion_id, payload)
    return CompanionRead.model_validate(companion)


@router.delete(
    "/{companion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "Компаньон не найден"}},
    summary="Удалить компаньона",
    description="Удаляет компаньона вместе с его диалогами и сообщениями.",
)
async def delete_companion(
    companion_id: UUID,
    companion_service: CompanionServiceDependency,
) -> None:
    await companion_service.delete(companion_id)


@router.post(
    "/{companion_id}/conversations",
    response_model=ConversationRead,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"description": "Компаньон не найден"}},
    summary="Создать диалог",
    description="Создаёт новый диалог с выбранным компаньоном.",
)
async def create_conversation(
    companion_id: UUID,
    conversation_service: ConversationServiceDependency,
) -> ConversationRead:
    conversation = await conversation_service.create(companion_id)
    return ConversationRead.model_validate(conversation)


@router.get(
    "/{companion_id}/conversations",
    response_model=list[ConversationRead],
    responses={404: {"description": "Компаньон не найден"}},
    summary="Получить диалоги компаньона",
    description="Возвращает диалоги выбранного компаньона, новые первыми.",
)
async def list_companion_conversations(
    companion_id: UUID,
    conversation_service: ConversationServiceDependency,
) -> list[ConversationRead]:
    conversations = await conversation_service.list_for_companion(companion_id)
    return [ConversationRead.model_validate(item) for item in conversations]
