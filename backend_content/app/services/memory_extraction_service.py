import json
import logging
from uuid import UUID

from pydantic import ValidationError

from app.errors import ConversationNotFoundError, LLMProviderError, MemoryExtractionError
from app.llm.base import LLMMessage, LLMProvider
from app.models.memory import Memory
from app.models.message import Message
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.memory_extraction import MemoryExtractionResult
from app.services.memory_management_service import MemoryManagementService

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """\
You extract long-term memories from a conversation between a user and an AI companion.

Return one JSON object and nothing else. No markdown, no code fences, no commentary.

Schema:
{"memories":[{"type":"<type>","content":"string","importance":0.0,"confidence":0.0}]}
type must be one of: fact, preference, goal, event, relationship.

Rules:
- Include only durable information: stable facts, preferences, personal goals,
  meaningful events, and important relationships.
- Each candidate must be explicitly supported by the user's messages.
  Do not invent facts or make unsupported assumptions.
- Assistant messages provide conversational context only.
  They are not evidence for facts about the user.
- Do not infer unstated conclusions.
  For example, mentioning a dog does not mean the user likes dogs.
- Do not store ordinary questions, temporary context, generic statements,
  request-only details, current-conversation instructions, or trivial details.
- Prefer a coherent set of current facts. Do not emit near-duplicate statements
  that restate the same information, and do not mix obsolete and current values
  for the same fact.
- importance: how useful this is likely to be later, from 0.0 to 1.0.
- confidence: how certain the memory is supported by the conversation, 0.0 to 1.0.
  Do not use confidence to justify unsupported assumptions.
- Write content as a concise standalone statement.
  Use the same language as the supporting user statement.
- If nothing qualifies, return {"memories":[]}.
"""


class MemoryExtractionService:
    def __init__(
        self,
        conversations: ConversationRepository,
        messages: MessageRepository,
        memory_management: MemoryManagementService,
        llm_provider: LLMProvider,
    ) -> None:
        self.conversations = conversations
        self.messages = messages
        self.memory_management = memory_management
        self.llm_provider = llm_provider

    async def extract_from_conversation(self, conversation_id: UUID) -> list[Memory]:
        conversation = await self.conversations.get(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError

        history = await self.messages.list_for_conversation(conversation_id)
        if not history:
            return []

        try:
            raw = await self.llm_provider.generate_response(_extraction_prompt(history))
        except LLMProviderError:
            logger.warning(
                "memory_extraction_llm_failed",
                extra={"conversation_id": str(conversation_id)},
                exc_info=True,
            )
            raise

        result = _parse_extraction_result(raw, conversation_id)
        if not result.memories:
            return []
        return await self.memory_management.ingest(
            conversation.companion_id,
            result.memories,
            source_conversation_id=conversation.id,
        )


def _extraction_prompt(history: list[Message]) -> list[LLMMessage]:
    return [
        LLMMessage(role="system", content=EXTRACTION_SYSTEM_PROMPT),
        *[LLMMessage(role=message.role.value, content=message.content) for message in history],
    ]


def _parse_extraction_result(raw: str, conversation_id: UUID) -> MemoryExtractionResult:
    try:
        payload = json.loads(raw)
        return MemoryExtractionResult.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning(
            "memory_extraction_invalid_output",
            extra={
                "conversation_id": str(conversation_id),
                "error_type": type(exc).__name__,
            },
        )
        raise MemoryExtractionError from exc
