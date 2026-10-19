from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class MemoryVectorMatch:
    """Semantic search hit from the vector index; not a canonical Memory."""

    memory_id: UUID
    score: float
    user_id: UUID | None = None
    companion_id: UUID | None = None
    is_active: bool | None = None
    memory_type: str | None = None


class MemoryVectorIndex(ABC):
    """Stores memory vectors and ownership metadata; not the source of truth."""

    @abstractmethod
    async def ensure_collection(self) -> None:
        """Create the collection if missing, or reject an incompatible one."""
        raise NotImplementedError

    @abstractmethod
    async def recreate(self) -> None:
        """Delete and recreate the collection so stale points disappear."""
        raise NotImplementedError

    @abstractmethod
    async def upsert(
        self,
        *,
        memory_id: UUID,
        vector: list[float],
        user_id: UUID,
        companion_id: UUID,
        memory_type: str,
        is_active: bool,
    ) -> None:
        """Insert or replace the point identified by `memory_id`."""
        raise NotImplementedError

    @abstractmethod
    async def update_payload(
        self,
        *,
        memory_id: UUID,
        user_id: UUID,
        companion_id: UUID,
        memory_type: str,
        is_active: bool,
    ) -> bool:
        """Update payload for an existing point. Returns False if it is missing."""
        raise NotImplementedError

    @abstractmethod
    async def delete_for_companion(self, user_id: UUID, companion_id: UUID) -> None:
        """Remove all points owned by this user and companion pair."""
        raise NotImplementedError

    @abstractmethod
    async def search(
        self,
        *,
        query: list[float],
        user_id: UUID,
        companion_id: UUID,
        top_k: int,
        score_threshold: float,
    ) -> list[MemoryVectorMatch]:
        """Return tenant-scoped active matches for `query`, best score first."""
        raise NotImplementedError

    async def aclose(self) -> None:
        """Release index client resources. Default is a no-op."""
        return None
