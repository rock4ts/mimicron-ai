import logging
import math
from typing import Self
from uuid import UUID

from qdrant_client import AsyncQdrantClient, models

from app.config import QdrantDistanceName, Settings
from app.errors import VectorIndexError
from app.vector_index.base import MemoryVectorIndex, MemoryVectorMatch

logger = logging.getLogger(__name__)

_DISTANCE: dict[QdrantDistanceName, models.Distance] = {
    "Cosine": models.Distance.COSINE,
    "Euclid": models.Distance.EUCLID,
    "Dot": models.Distance.DOT,
    "Manhattan": models.Distance.MANHATTAN,
}

_PAYLOAD_INDEXES: tuple[tuple[str, models.PayloadSchemaType], ...] = (
    ("user_id", models.PayloadSchemaType.KEYWORD),
    ("companion_id", models.PayloadSchemaType.KEYWORD),
    ("memory_type", models.PayloadSchemaType.KEYWORD),
    ("is_active", models.PayloadSchemaType.BOOL),
)


class QdrantMemoryVectorIndex(MemoryVectorIndex):
    """Qdrant adapter using Memory UUID point IDs and tenant payload metadata."""

    def __init__(
        self,
        *,
        url: str,
        collection: str,
        dimensions: int,
        distance: QdrantDistanceName,
        api_key: str = "",
        timeout_seconds: float = 5.0,
        client: AsyncQdrantClient | None = None,
    ) -> None:
        self._collection = collection
        self._dimensions = dimensions
        self._distance = _DISTANCE[distance]
        self._client = client or AsyncQdrantClient(
            url=url,
            api_key=api_key or None,
            timeout=max(1, int(timeout_seconds)),
            check_compatibility=False,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        """Build a client from Qdrant settings and embedding dimensions."""
        return cls(
            url=settings.qdrant.url,
            api_key=settings.qdrant.api_key,
            collection=settings.qdrant.collection,
            dimensions=settings.embedding.dimensions,
            distance=settings.qdrant.distance,
            timeout_seconds=settings.qdrant.timeout_seconds,
        )

    async def ensure_collection(self) -> None:
        """Create the collection if missing, or reject an incompatible one."""
        try:
            exists = await self._client.collection_exists(self._collection)
            if not exists:
                await self._create_collection()
                return
            await self._assert_compatible()
            await self._ensure_payload_indexes()
        except VectorIndexError:
            raise
        except Exception as exc:
            raise VectorIndexError("Qdrant request failed") from exc

    async def recreate(self) -> None:
        """Delete and recreate the collection so stale points disappear."""
        try:
            if await self._client.collection_exists(self._collection):
                await self._client.delete_collection(self._collection)
            await self._create_collection()
        except VectorIndexError:
            raise
        except Exception as exc:
            raise VectorIndexError("Qdrant request failed") from exc

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
        await self.ensure_collection()
        try:
            await self._client.upsert(
                collection_name=self._collection,
                points=[
                    models.PointStruct(
                        id=str(memory_id),
                        vector=vector,
                        payload=_payload(
                            memory_id=memory_id,
                            user_id=user_id,
                            companion_id=companion_id,
                            memory_type=memory_type,
                            is_active=is_active,
                        ),
                    )
                ],
            )
        except Exception as exc:
            raise VectorIndexError("Qdrant request failed") from exc

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
        await self.ensure_collection()
        try:
            existing = await self._client.retrieve(
                collection_name=self._collection,
                ids=[str(memory_id)],
                with_payload=False,
                with_vectors=False,
            )
            if not existing:
                return False
            _ = await self._client.set_payload(
                collection_name=self._collection,
                payload=_payload(
                    memory_id=memory_id,
                    user_id=user_id,
                    companion_id=companion_id,
                    memory_type=memory_type,
                    is_active=is_active,
                ),
                points=[str(memory_id)],
            )
            return True
        except Exception as exc:
            raise VectorIndexError("Qdrant request failed") from exc

    async def delete_for_companion(self, user_id: UUID, companion_id: UUID) -> None:
        """Remove all points owned by this user and companion pair."""
        await self.ensure_collection()
        try:
            await self._client.delete(
                collection_name=self._collection,
                points_selector=models.FilterSelector(
                    filter=_owner_filter(user_id, companion_id),
                ),
            )
        except Exception as exc:
            raise VectorIndexError("Qdrant request failed") from exc

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
        try:
            response = await self._client.query_points(
                collection_name=self._collection,
                query=query,
                query_filter=_owner_active_filter(user_id, companion_id),
                limit=top_k,
                score_threshold=score_threshold,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:
            raise VectorIndexError("Qdrant request failed") from exc

        matches: list[MemoryVectorMatch] = []
        for point in response.points:
            match = _match_from_point(point)
            if match is None:
                logger.warning(
                    "memory_vector_match_invalid",
                    extra={"error_type": "InvalidVectorMatch"},
                )
                continue
            matches.append(match)
        return matches

    async def aclose(self) -> None:
        """Close the Qdrant client."""
        await self._client.close()

    async def _create_collection(self) -> None:
        await self._client.create_collection(
            collection_name=self._collection,
            vectors_config=models.VectorParams(
                size=self._dimensions,
                distance=self._distance,
            ),
        )
        await self._ensure_payload_indexes()

    async def _assert_compatible(self) -> None:
        info = await self._client.get_collection(self._collection)
        vectors = info.config.params.vectors
        if not isinstance(vectors, models.VectorParams):
            raise VectorIndexError("Qdrant collection uses incompatible vector configuration")
        if vectors.size != self._dimensions or vectors.distance != self._distance:
            raise VectorIndexError("Qdrant collection does not match embedding configuration")

    async def _ensure_payload_indexes(self) -> None:
        info = await self._client.get_collection(self._collection)
        existing = set(info.payload_schema.keys()) if info.payload_schema else set()
        for field_name, schema in _PAYLOAD_INDEXES:
            if field_name in existing:
                continue
            await self._client.create_payload_index(
                collection_name=self._collection,
                field_name=field_name,
                field_schema=schema,
            )


def _payload(
    *,
    memory_id: UUID,
    user_id: UUID,
    companion_id: UUID,
    memory_type: str,
    is_active: bool,
) -> dict[str, str | bool]:
    return {
        "memory_id": str(memory_id),
        "user_id": str(user_id),
        "companion_id": str(companion_id),
        "memory_type": memory_type,
        "is_active": is_active,
    }


def _owner_filter(user_id: UUID, companion_id: UUID) -> models.Filter:
    return models.Filter(
        must=[
            models.FieldCondition(
                key="user_id",
                match=models.MatchValue(value=str(user_id)),
            ),
            models.FieldCondition(
                key="companion_id",
                match=models.MatchValue(value=str(companion_id)),
            ),
        ]
    )


def _owner_active_filter(user_id: UUID, companion_id: UUID) -> models.Filter:
    return models.Filter(
        must=[
            models.FieldCondition(
                key="user_id",
                match=models.MatchValue(value=str(user_id)),
            ),
            models.FieldCondition(
                key="companion_id",
                match=models.MatchValue(value=str(companion_id)),
            ),
            models.FieldCondition(
                key="is_active",
                match=models.MatchValue(value=True),
            ),
        ]
    )


def _as_uuid(value: object) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _as_finite_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    score = float(value)
    if not math.isfinite(score):
        return None
    return score


def _match_from_point(point: models.ScoredPoint) -> MemoryVectorMatch | None:
    payload = point.payload or {}
    memory_id = _as_uuid(payload.get("memory_id")) or _as_uuid(point.id)
    score = _as_finite_float(point.score)
    if memory_id is None or score is None:
        return None
    is_active = payload.get("is_active")
    memory_type = payload.get("memory_type")
    return MemoryVectorMatch(
        memory_id=memory_id,
        score=score,
        user_id=_as_uuid(payload.get("user_id")),
        companion_id=_as_uuid(payload.get("companion_id")),
        is_active=is_active if isinstance(is_active, bool) else None,
        memory_type=str(memory_type) if memory_type is not None else None,
    )
