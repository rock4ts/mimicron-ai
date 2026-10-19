from uuid import UUID

from app.errors import CompanionNotFoundError, ConversationNotFoundError
from app.models.conversation import Conversation
from app.models.message import Message
from app.repositories.companion_repository import CompanionRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository


class ConversationService:
    def __init__(
        self,
        companions: CompanionRepository,
        conversations: ConversationRepository,
        messages: MessageRepository,
    ) -> None:
        self.companions = companions
        self.conversations = conversations
        self.messages = messages

    async def create(self, companion_id: UUID) -> Conversation:
        if await self.companions.get(companion_id) is None:
            raise CompanionNotFoundError
        conversation = await self.conversations.create(companion_id)
        await self.conversations.uow.commit()
        await self.conversations.uow.refresh(conversation)
        return conversation

    async def get(self, conversation_id: UUID) -> Conversation:
        conversation = await self.conversations.get(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError
        return conversation

    async def list_for_companion(self, companion_id: UUID) -> list[Conversation]:
        if await self.companions.get(companion_id) is None:
            raise CompanionNotFoundError
        return await self.conversations.list_for_companion(companion_id)

    async def list_messages(self, conversation_id: UUID) -> list[Message]:
        await self.get(conversation_id)
        return await self.messages.list_for_conversation(conversation_id)
