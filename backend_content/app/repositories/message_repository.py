from uuid import UUID

from sqlalchemy import select

from app.db.uow import UnitOfWork
from app.models.message import Message, MessageRole


class MessageRepository:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def create(
        self,
        conversation_id: UUID,
        role: MessageRole,
        content: str,
    ) -> Message:
        message = Message(conversation_id=conversation_id, role=role, content=content)
        self.uow.session.add(message)
        await self.uow.session.flush()
        return message

    async def list_for_conversation(self, conversation_id: UUID) -> list[Message]:
        result = await self.uow.session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at, Message.id)
        )
        return list(result)
