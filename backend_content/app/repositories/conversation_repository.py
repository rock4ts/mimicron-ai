from uuid import UUID

from sqlalchemy import select, update

from app.db.uow import UnitOfWork
from app.models.companion import Companion
from app.models.conversation import Conversation


class ConversationRepository:
    def __init__(self, uow: UnitOfWork, user_id: UUID) -> None:
        self.uow = uow
        self.user_id = user_id

    async def create(self, companion_id: UUID) -> Conversation:
        conversation = Conversation(companion_id=companion_id)
        self.uow.session.add(conversation)
        await self.uow.session.flush()
        return conversation

    async def get(self, conversation_id: UUID) -> Conversation | None:
        result = await self.uow.session.scalars(
            select(Conversation)
            .join(Companion, Conversation.companion_id == Companion.id)
            .where(
                Conversation.id == conversation_id,
                Companion.user_id == self.user_id,
            )
        )
        return result.first()

    async def list_for_companion(self, companion_id: UUID) -> list[Conversation]:
        result = await self.uow.session.scalars(
            select(Conversation)
            .join(Companion, Conversation.companion_id == Companion.id)
            .where(
                Conversation.companion_id == companion_id,
                Companion.user_id == self.user_id,
            )
            .order_by(Conversation.created_at.desc(), Conversation.id.desc())
        )
        return list(result)

    async def set_title_if_empty(self, conversation_id: UUID, title: str) -> None:
        await self.uow.session.execute(
            update(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.title.is_(None),
            )
            .values(title=title)
        )
