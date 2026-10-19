from app.config import Settings
from app.vector_index.base import MemoryVectorIndex, MemoryVectorMatch
from app.vector_index.qdrant import QdrantMemoryVectorIndex

__all__ = [
    "MemoryVectorIndex",
    "MemoryVectorMatch",
    "QdrantMemoryVectorIndex",
    "create_vector_index",
]


def create_vector_index(settings: Settings) -> MemoryVectorIndex:
    """Build the Qdrant memory index from application settings."""
    return QdrantMemoryVectorIndex.from_settings(settings)
