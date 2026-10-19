from pydantic import BaseModel

from app.config import get_settings
from app.main import create_app
from app.vector_index import create_vector_index
from tests.functional.fakes import (
    ControllableMemoryVectorIndex,
    FakeEmbeddingProvider,
    FakeLLMProvider,
)


class LLMConfiguration(BaseModel):
    responses: list[str] = []
    error: str | None = None
    error_on_call: int | None = None
    delay_seconds: float = 0.0


class EmbeddingConfiguration(BaseModel):
    vectors: dict[str, list[float]] = {}
    error: str | None = None
    error_on_call: int | None = None


class VectorIndexConfiguration(BaseModel):
    error: str | None = None


_settings = get_settings()
fake_llm = FakeLLMProvider(timeout_seconds=_settings.llm_timeout_seconds)
fake_embeddings = FakeEmbeddingProvider(dimensions=_settings.embedding.dimensions)
vector_index = ControllableMemoryVectorIndex(create_vector_index(_settings))
app = create_app(
    llm_provider=fake_llm,
    embedding_provider=fake_embeddings,
    vector_index=vector_index,
)


@app.post("/__test__/llm_reset", include_in_schema=False)
async def reset() -> dict[str, str]:
    fake_llm.reset()
    fake_embeddings.reset()
    vector_index.error = None
    return {"status": "reset"}


@app.put("/__test__/llm", include_in_schema=False)
async def configure_llm(configuration: LLMConfiguration) -> dict[str, str]:
    fake_llm.responses = configuration.responses.copy()
    fake_llm.error = configuration.error
    fake_llm.error_on_call = configuration.error_on_call
    fake_llm.delay_seconds = configuration.delay_seconds
    return {"status": "configured"}


@app.get("/__test__/llm/calls", include_in_schema=False)
async def llm_calls() -> list[list[dict[str, str]]]:
    return [
        [{"role": message.role, "content": message.content} for message in call]
        for call in fake_llm.calls
    ]


@app.put("/__test__/embeddings", include_in_schema=False)
async def configure_embeddings(configuration: EmbeddingConfiguration) -> dict[str, str]:
    fake_embeddings.vectors = {text: list(vector) for text, vector in configuration.vectors.items()}
    fake_embeddings.error = configuration.error
    fake_embeddings.error_on_call = configuration.error_on_call
    return {"status": "configured"}


@app.get("/__test__/embeddings/calls", include_in_schema=False)
async def embedding_calls() -> list[str]:
    return list(fake_embeddings.calls)


@app.put("/__test__/vector_index", include_in_schema=False)
async def configure_vector_index(configuration: VectorIndexConfiguration) -> dict[str, str]:
    vector_index.error = configuration.error
    return {"status": "configured"}
