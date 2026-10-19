from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class LLMMessage:
    role: Literal["system", "user", "assistant"]
    content: str


class LLMProvider(ABC):
    @abstractmethod
    async def generate_response(self, messages: list[LLMMessage]) -> str:
        raise NotImplementedError

    async def aclose(self) -> None:
        return None
