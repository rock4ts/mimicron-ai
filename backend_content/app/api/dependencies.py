import logging
from collections.abc import AsyncIterator
from typing import Annotated, cast

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.uow import UnitOfWork
from app.embeddings.base import EmbeddingProvider
from app.errors import InvalidTokenError
from app.llm.base import LLMProvider
from app.repositories.companion_repository import CompanionRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.memory_repository import MemoryRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.auth import AccessTokenPayload
from app.services.chat_service import ChatService
from app.services.companion_service import CompanionService
from app.services.conversation_service import ConversationService
from app.services.memory_extraction_service import MemoryExtractionService
from app.services.memory_indexing_service import MemoryIndexingService
from app.services.memory_management_service import MemoryManagementService
from app.services.memory_retrieval_service import MemoryRetrievalService
from app.services.memory_service import MemoryService
from app.vector_index.base import MemoryVectorIndex

logger = logging.getLogger(__name__)
oauth2_scheme = HTTPBearer(auto_error=False)


def get_settings_from_app(request: Request) -> Settings:
    return request.app.state.settings


async def get_uow(request: Request) -> AsyncIterator[UnitOfWork]:
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with session_factory() as session:
        yield UnitOfWork(session)


async def get_llm_provider(request: Request) -> AsyncIterator[LLMProvider]:
    provider: LLMProvider = request.app.state.llm_provider
    yield provider


def get_access_token_payload(
    token: Annotated[HTTPAuthorizationCredentials | None, Depends(oauth2_scheme)],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
) -> AccessTokenPayload:
    if token is None:
        raise InvalidTokenError("Not authenticated")
    try:
        payload = cast(
            dict[str, object],
            jwt.decode(
                token.credentials,
                settings.jwt.public_key,
                algorithms=[settings.jwt.algorithm],
            ),
        )
    except jwt.ExpiredSignatureError:
        raise InvalidTokenError("Token has expired") from None
    except jwt.InvalidTokenError:
        logger.info("invalid_access_token")
        raise InvalidTokenError() from None

    try:
        validated_payload = AccessTokenPayload.model_validate(payload)
    except ValidationError:
        raise InvalidTokenError("Invalid token payload") from None
    if validated_payload.type != "access":
        raise InvalidTokenError("Token is not an access token")
    return validated_payload


UowDependency = Annotated[UnitOfWork, Depends(get_uow)]
LLMDependency = Annotated[LLMProvider, Depends(get_llm_provider)]
AccessTokenPayloadDependency = Annotated[AccessTokenPayload, Depends(get_access_token_payload)]


def get_memory_indexing_service(request: Request) -> MemoryIndexingService:
    return request.app.state.memory_indexing_service


def get_embedding_provider(request: Request) -> EmbeddingProvider:
    return request.app.state.embedding_provider


def get_vector_index(request: Request) -> MemoryVectorIndex:
    return request.app.state.vector_index


MemoryIndexingDependency = Annotated[MemoryIndexingService, Depends(get_memory_indexing_service)]
EmbeddingProviderDependency = Annotated[EmbeddingProvider, Depends(get_embedding_provider)]
VectorIndexDependency = Annotated[MemoryVectorIndex, Depends(get_vector_index)]


def get_companion_service(
    uow: UowDependency,
    payload: AccessTokenPayloadDependency,
    indexing: MemoryIndexingDependency,
) -> CompanionService:
    return CompanionService(CompanionRepository(uow, payload.sub), indexing)


def get_memory_service(
    uow: UowDependency,
    payload: AccessTokenPayloadDependency,
    indexing: MemoryIndexingDependency,
) -> MemoryService:
    user_id = payload.sub
    return MemoryService(
        CompanionRepository(uow, user_id),
        MemoryRepository(uow, user_id),
        indexing,
    )


def get_memory_retrieval_service(
    uow: UowDependency,
    payload: AccessTokenPayloadDependency,
    embeddings: EmbeddingProviderDependency,
    vector_index: VectorIndexDependency,
    settings: Annotated[Settings, Depends(get_settings_from_app)],
) -> MemoryRetrievalService:
    return MemoryRetrievalService(
        embeddings,
        vector_index,
        MemoryRepository(uow, payload.sub),
        top_k=settings.memory_retrieval.top_k,
        score_threshold=settings.memory_retrieval.score_threshold,
    )


def get_conversation_service(
    uow: UowDependency,
    payload: AccessTokenPayloadDependency,
) -> ConversationService:
    user_id = payload.sub
    return ConversationService(
        CompanionRepository(uow, user_id),
        ConversationRepository(uow, user_id),
        MessageRepository(uow),
    )


def get_chat_service(
    uow: UowDependency,
    llm_provider: LLMDependency,
    payload: AccessTokenPayloadDependency,
    retrieval: Annotated[MemoryRetrievalService, Depends(get_memory_retrieval_service)],
) -> ChatService:
    user_id = payload.sub
    return ChatService(
        CompanionRepository(uow, user_id),
        ConversationRepository(uow, user_id),
        MessageRepository(uow),
        llm_provider,
        retrieval,
    )


def get_memory_management_service(
    uow: UowDependency,
    payload: AccessTokenPayloadDependency,
    indexing: MemoryIndexingDependency,
    embeddings: EmbeddingProviderDependency,
    vector_index: VectorIndexDependency,
    llm_provider: LLMDependency,
    settings: Annotated[Settings, Depends(get_settings_from_app)],
) -> MemoryManagementService:
    user_id = payload.sub
    return MemoryManagementService(
        CompanionRepository(uow, user_id),
        MemoryRepository(uow, user_id),
        indexing,
        embeddings,
        vector_index,
        llm_provider,
        top_k=settings.memory_management.top_k,
        score_threshold=settings.memory_management.score_threshold,
    )


def get_memory_extraction_service(
    uow: UowDependency,
    payload: AccessTokenPayloadDependency,
    llm_provider: LLMDependency,
    management: Annotated[MemoryManagementService, Depends(get_memory_management_service)],
) -> MemoryExtractionService:
    return MemoryExtractionService(
        ConversationRepository(uow, payload.sub),
        MessageRepository(uow),
        management,
        llm_provider,
    )


CompanionServiceDependency = Annotated[CompanionService, Depends(get_companion_service)]
ConversationServiceDependency = Annotated[ConversationService, Depends(get_conversation_service)]
ChatServiceDependency = Annotated[ChatService, Depends(get_chat_service)]
MemoryServiceDependency = Annotated[MemoryService, Depends(get_memory_service)]
MemoryManagementServiceDependency = Annotated[
    MemoryManagementService, Depends(get_memory_management_service)
]
MemoryExtractionServiceDependency = Annotated[
    MemoryExtractionService, Depends(get_memory_extraction_service)
]
