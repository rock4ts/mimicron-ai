import asyncio
import logging
from typing import Any

from gigachat import GigaChat
from gigachat.models import ChatCompletionRequest, ChatMessage

from app.errors import LLMProviderError
from app.llm.base import LLMMessage, LLMProvider

logger = logging.getLogger(__name__)


class GigachatProvider(LLMProvider):
    def __init__(self, api_key: str, model: str, timeout_seconds: float = 60.0) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def generate_response(self, messages: list[LLMMessage]) -> str:
        if not self.api_key:
            raise LLMProviderError("LLM is not configured")

        request = ChatCompletionRequest(
            model=self.model,
            messages=[ChatMessage(role=item.role, content=item.content) for item in messages],
        )
        try:
            response = await asyncio.wait_for(
                self._create(request),
                timeout=self.timeout_seconds,
            )
            content = self._extract_text(response)
            if not content:
                raise LLMProviderError("LLM returned an empty response")
            return content
        except TimeoutError as exc:
            logger.error(
                "llm_request_timed_out",
                extra={"provider": "gigachat", "timeout_seconds": self.timeout_seconds},
            )
            raise LLMProviderError("LLM request timed out") from exc
        except LLMProviderError:
            raise
        except Exception as exc:
            logger.error(
                "llm_request_failed",
                extra={"provider": "gigachat", "error_type": type(exc).__name__},
            )
            raise LLMProviderError("LLM request failed") from exc

    async def _create(self, request: ChatCompletionRequest) -> Any:
        async with GigaChat(
            credentials=self.api_key,
            model=self.model,
            # TODO: enable SSL verification after adding Russian CA chain
            verify_ssl_certs=False,
        ) as client:
            return await client.achat.create(request)

    @staticmethod
    def _extract_text(response: Any) -> str:
        if not getattr(response, "messages", None):
            return ""
        content = response.messages[0].content
        if isinstance(content, str):
            return content.strip()
        for part in content or []:
            text = part.get("text") if isinstance(part, dict) else getattr(part, "text", None)
            if text:
                return str(text).strip()
        return ""
