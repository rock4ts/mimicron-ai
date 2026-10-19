import json
import logging
from datetime import UTC, datetime
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in (
            "request_id",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "provider",
            "error_type",
            "timeout_seconds",
            "memory_id",
            "companion_id",
            "user_id",
            "conversation_id",
            "top_k",
            "candidate_count",
            "candidate_index",
            "decision_count",
            "included_count",
            "embedding_duration_ms",
            "qdrant_duration_ms",
            "postgres_duration_ms",
            "retrieval_stage",
            "relation",
            "action",
            "existing_memory_id",
            "superseded_memory_id",
            "index_sync_pending",
            "attempt_count",
            "created_count",
            "deactivated_count",
            "duplicate_count",
            "discarded_count",
            "synced_count",
            "failed_count",
        ):
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(
        level=level.upper(),
        handlers=[handler],
        force=True,
    )
