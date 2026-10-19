"""Rebuild the Qdrant memory index from active PostgreSQL memories."""

import argparse
import asyncio
import sys

from app.config import get_settings
from app.db.session import create_engine_and_session_factory
from app.db.uow import UnitOfWork
from app.embeddings import create_embedding_provider
from app.errors import VectorIndexError
from app.logging import configure_logging
from app.services.memory_indexing_service import MemoryIndexingService, reindex_active_memories
from app.vector_index import create_vector_index


async def _run(batch_size: int) -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    engine, session_factory = create_engine_and_session_factory(settings.postgres.url)
    embeddings = create_embedding_provider(settings)
    vector_index = create_vector_index(settings)
    indexing = MemoryIndexingService(embeddings, vector_index)
    try:
        async with session_factory() as session:
            indexed, failed = await reindex_active_memories(
                UnitOfWork(session),
                indexing,
                vector_index,
                batch_size=batch_size,
            )
    except VectorIndexError:
        print("Failed to recreate the Qdrant collection", file=sys.stderr)
        return 1
    finally:
        await embeddings.aclose()
        await vector_index.aclose()
        await engine.dispose()

    print(f"Indexed: {indexed}")
    print(f"Failed: {failed}")
    return 1 if failed else 0


def main() -> None:
    """Parse CLI flags and exit non-zero if any memory failed to index."""
    parser = argparse.ArgumentParser(
        description="Rebuild the Qdrant memory index from active PostgreSQL memories",
    )
    parser.add_argument("--batch-size", type=int, default=100, metavar="N")
    args = parser.parse_args()
    if args.batch_size < 1:
        print("batch-size must be a positive integer", file=sys.stderr)
        sys.exit(1)
    sys.exit(asyncio.run(_run(args.batch_size)))


if __name__ == "__main__":
    main()
