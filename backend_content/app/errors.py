class MimicronError(Exception):
    """Base application error."""


class InvalidTokenError(MimicronError):
    def __init__(self, detail: str = "Invalid token") -> None:
        super().__init__(detail)


class CompanionNotFoundError(MimicronError):
    pass


class ConversationNotFoundError(MimicronError):
    pass


class MemoryNotFoundError(MimicronError):
    pass


class MemoryExtractionError(MimicronError):
    pass


class MemoryReconciliationError(MimicronError):
    """LLM reconciliation output is invalid or internally inconsistent."""


class MemoryIndexOutOfSyncError(MimicronError):
    """Canonical memories are pending index sync and the index is not usable."""


class LLMProviderError(MimicronError):
    pass


class EmbeddingProviderError(MimicronError):
    """Embedding request failed, timed out, or returned an invalid vector."""


class VectorIndexError(MimicronError):
    """Qdrant request failed or the collection is incompatible."""
