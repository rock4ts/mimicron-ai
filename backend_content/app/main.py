import logging
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.routes.companions import router as companions_router
from app.api.routes.conversations import router as conversations_router
from app.api.routes.messages import router as messages_router
from app.config import Settings, get_settings
from app.db.session import create_engine_and_session_factory
from app.embeddings import create_embedding_provider
from app.embeddings.base import EmbeddingProvider
from app.errors import (
    CompanionNotFoundError,
    ConversationNotFoundError,
    InvalidTokenError,
    LLMProviderError,
    VectorIndexError,
)
from app.llm.base import LLMProvider
from app.llm.gigachat import GigachatProvider
from app.logging import configure_logging
from app.services.memory_indexing_service import MemoryIndexingService
from app.vector_index import MemoryVectorIndex, create_vector_index
from app.web.routes import html_error_if_app

# from app.web.routes import router as web_router
from app.web.templates import STATIC_DIR

logger = logging.getLogger(__name__)


def _unauthorized(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": detail},
        headers={"WWW-Authenticate": "Bearer"},
    )


def create_app(
    settings: Settings | None = None,
    llm_provider: LLMProvider | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    vector_index: MemoryVectorIndex | None = None,
) -> FastAPI:
    application_settings = settings or get_settings()
    configure_logging(application_settings.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
        engine, session_factory = create_engine_and_session_factory(
            application_settings.postgres.url
        )
        resolved_embedding_provider = embedding_provider or create_embedding_provider(
            application_settings
        )
        resolved_vector_index = vector_index or create_vector_index(application_settings)
        application.state.settings = application_settings
        application.state.session_factory = session_factory
        application.state.llm_provider = llm_provider or GigachatProvider(
            application_settings.llm_api_key,
            application_settings.llm_model,
            timeout_seconds=application_settings.llm_timeout_seconds,
        )
        application.state.embedding_provider = resolved_embedding_provider
        application.state.vector_index = resolved_vector_index
        application.state.memory_indexing_service = MemoryIndexingService(
            resolved_embedding_provider,
            resolved_vector_index,
        )
        try:
            await resolved_vector_index.ensure_collection()
        except VectorIndexError:
            logger.warning(
                "qdrant_collection_init_failed",
                extra={"error_type": "VectorIndexError"},
                exc_info=True,
            )
        try:
            yield
        finally:
            await resolved_embedding_provider.aclose()
            await resolved_vector_index.aclose()
            await engine.dispose()

    application = FastAPI(
        title="Mimicron API",
        description=(
            "Backend API для AI-компаньонов и диалогов с памятью в PostgreSQL "
            "и семантическим поиском в Qdrant."
        ),
        version="0.1.0",
        lifespan=lifespan,
        root_path=application_settings.root_path,
    )
    application.state.settings = application_settings
    application.include_router(companions_router)
    application.include_router(conversations_router)
    application.include_router(messages_router)
    # application.include_router(web_router)
    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @application.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/docs")
        # return RedirectResponse(url="/ui")

    @application.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.middleware("http")
    async def log_request(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        header_name = application_settings.request_id_header
        request_id = request.headers.get(header_name, str(uuid4()))
        started_at = time.perf_counter()
        response = await call_next(request)
        response.headers[header_name] = request_id
        logger.info(
            "http_request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
            },
        )
        return response

    @application.exception_handler(InvalidTokenError)
    async def invalid_token(_request: Request, exc: InvalidTokenError) -> JSONResponse:
        return _unauthorized(str(exc))

    @application.exception_handler(RequestValidationError)
    @html_error_if_app(
        title="Invalid request",
        message="Check the address or submitted values and try again.",
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )
    async def request_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> Response:
        return await request_validation_exception_handler(request, exc)

    @application.exception_handler(CompanionNotFoundError)
    @html_error_if_app(
        title="Companion not found",
        message="This companion may have been deleted.",
        status_code=status.HTTP_404_NOT_FOUND,
    )
    async def companion_not_found(
        _request: Request,
        _: CompanionNotFoundError,
    ) -> Response:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "Companion not found"},
        )

    @application.exception_handler(ConversationNotFoundError)
    @html_error_if_app(
        title="Conversation not found",
        message="This conversation may have been deleted.",
        status_code=status.HTTP_404_NOT_FOUND,
    )
    async def conversation_not_found(
        _request: Request,
        _: ConversationNotFoundError,
    ) -> Response:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "Conversation not found"},
        )

    @application.exception_handler(LLMProviderError)
    @html_error_if_app(
        title="Reply unavailable",
        message="The AI provider is temporarily unavailable. Please try again.",
        status_code=status.HTTP_502_BAD_GATEWAY,
    )
    async def llm_error(_request: Request, exc: LLMProviderError) -> Response:
        logger.error(
            "llm_provider_error",
            extra={"error_type": type(exc).__name__},
        )
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": "LLM provider is temporarily unavailable"},
        )

    @application.exception_handler(Exception)
    @html_error_if_app(
        title="Something went wrong",
        message="The request could not be completed. Please try again.",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
    async def unexpected_error(_request: Request, exc: Exception) -> Response:
        logger.error("unhandled_error", exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )

    return application


app = create_app()
