import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError

from app.embeddings.base import EmbeddingProvider
from app.errors import (
    CompanionNotFoundError,
    LLMProviderError,
    MemoryIndexOutOfSyncError,
    MemoryReconciliationError,
)
from app.llm.base import LLMMessage, LLMProvider
from app.models.memory import DeactivationReason, Memory, normalize_memory_content
from app.repositories.companion_repository import CompanionRepository
from app.repositories.memory_repository import MemoryRepository
from app.schemas.memory_extraction import MemoryCandidate
from app.schemas.memory_management import (
    MemoryReconciliationDecision,
    MemoryReconciliationResult,
    MemoryRelation,
)
from app.services.memory_indexing_service import MemoryIndexingService, project_and_clear_pending
from app.vector_index.base import MemoryVectorIndex

logger = logging.getLogger(__name__)

RECONCILIATION_SYSTEM_PROMPT = """\
You reconcile newly extracted memory candidates against existing active memories
for the same user and companion.

Return one JSON object and nothing else. No markdown, no code fences, no commentary.

Schema:
{"decisions":[{"candidate_index":0,"relation":"<relation>","existing_memory_id":"<uuid>"}]}

relation must be one of: duplicate, update, contradiction, additional, unrelated, discard.

Rules:
- Decide exactly once for every supplied candidate_index. Do not omit or repeat indices.
- duplicate: the candidate restates an existing memory. Set existing_memory_id.
  Do not create a new row.
- update: the candidate replaces the current value of an existing memory with a
  mutually exclusive newer fact. Set existing_memory_id. The old memory will be
  deactivated and the candidate will become the active replacement.
- contradiction: the candidate negates or conflicts with an existing current fact.
  Set existing_memory_id. Same lifecycle as update.
- additional: the candidate adds related information without replacing the existing
  fact. Omit existing_memory_id. Create a new memory and keep existing ones active.
- unrelated: the candidate is a new independent memory. Omit existing_memory_id.
- discard: the candidate is low-value, ephemeral, or not worth storing.
  Omit existing_memory_id. Persist nothing.
- existing_memory_id must be one of the supplied existing memory ids.
  Use it only for duplicate, update, and contradiction.
- Do not assume that semantic similarity means replacement. "User has a dog named
  Charlie." and "User's dog Charlie is three years old." is additional, not update.
- "User lives in Amsterdam." vs "User moved to Rotterdam." is update or contradiction.
- "User is learning Python." vs "User stopped learning Python." is contradiction.
- importance and confidence are imperfect extractor signals, not absolute truth.
  Prefer stable facts, useful preferences, meaningful goals, significant events,
  and reliable information. Discard trivial or unstable statements.
- If two candidates in this batch restate the same fact, keep one as
  unrelated/additional/update and discard the rest.
- Never reactivate or rewrite an existing memory in place.
"""


class MemoryManagementService:
    """Decides how extracted candidates change the canonical memory set."""

    def __init__(
        self,
        companions: CompanionRepository,
        memories: MemoryRepository,
        indexing: MemoryIndexingService,
        embeddings: EmbeddingProvider,
        vector_index: MemoryVectorIndex,
        llm_provider: LLMProvider,
        *,
        top_k: int,
        score_threshold: float,
    ) -> None:
        self.companions = companions
        self.memories = memories
        self.indexing = indexing
        self.embeddings = embeddings
        self.vector_index = vector_index
        self.llm_provider = llm_provider
        self.top_k = top_k
        self.score_threshold = score_threshold

    async def ingest(
        self,
        companion_id: UUID,
        candidates: Sequence[MemoryCandidate],
        *,
        source_conversation_id: UUID | None = None,
    ) -> list[Memory]:
        if await self.companions.get(companion_id) is None:
            raise CompanionNotFoundError
        if not candidates:
            return []

        decisions: dict[int, MemoryReconciliationDecision] = {}
        remaining: list[tuple[int, MemoryCandidate]] = []
        seen_normalized: dict[str, int] = {}

        for index, candidate in enumerate(candidates):
            key = normalize_memory_content(candidate.content)
            first_index = seen_normalized.get(key)
            if first_index is not None:
                decisions[index] = MemoryReconciliationDecision(
                    candidate_index=index,
                    relation=MemoryRelation.DISCARD,
                )
                logger.info(
                    "memory_reconciliation_duplicate",
                    extra={
                        "companion_id": str(companion_id),
                        "user_id": str(self.memories.user_id),
                        "candidate_index": index,
                        "relation": MemoryRelation.DISCARD.value,
                        "action": "batch_exact",
                    },
                )
                continue
            seen_normalized[key] = index
            existing = await self.memories.find_active_by_normalized_content(
                companion_id,
                candidate.content,
            )
            if existing is not None:
                decisions[index] = MemoryReconciliationDecision(
                    candidate_index=index,
                    relation=MemoryRelation.DUPLICATE,
                    existing_memory_id=existing.id,
                )
                logger.info(
                    "memory_reconciliation_duplicate",
                    extra={
                        "companion_id": str(companion_id),
                        "user_id": str(self.memories.user_id),
                        "candidate_index": index,
                        "relation": MemoryRelation.DUPLICATE.value,
                        "existing_memory_id": str(existing.id),
                        "action": "exact",
                    },
                )
                continue
            remaining.append((index, candidate))

        if remaining:
            await self._ensure_index_usable(companion_id)
            neighbors = await self._search_neighbors(companion_id, remaining)
            llm_decisions = await self._classify(remaining, neighbors)
            decisions.update(llm_decisions)

        created = await self._apply(
            companion_id,
            candidates,
            decisions,
            source_conversation_id=source_conversation_id,
        )
        logger.info(
            "memory_reconciliation_completed",
            extra={
                "companion_id": str(companion_id),
                "user_id": str(self.memories.user_id),
                "conversation_id": (
                    str(source_conversation_id) if source_conversation_id is not None else None
                ),
                "candidate_count": len(candidates),
                "decision_count": len(decisions),
                "created_count": len(created),
                "duplicate_count": sum(
                    1 for item in decisions.values() if item.relation is MemoryRelation.DUPLICATE
                ),
                "discarded_count": sum(
                    1 for item in decisions.values() if item.relation is MemoryRelation.DISCARD
                ),
                "deactivated_count": sum(
                    1
                    for item in decisions.values()
                    if item.relation in {MemoryRelation.UPDATE, MemoryRelation.CONTRADICTION}
                ),
            },
        )
        return created

    async def _ensure_index_usable(self, companion_id: UUID) -> None:
        pending = await self.memories.list_pending_for_companion(companion_id)
        for memory in pending:
            await project_and_clear_pending(self.indexing, memory, self.memories.uow)
        remaining_pending = await self.memories.list_pending_for_companion(companion_id)
        active_pending = [memory for memory in remaining_pending if memory.is_active]
        if not active_pending:
            return
        logger.warning(
            "memory_index_unusable",
            extra={
                "companion_id": str(companion_id),
                "user_id": str(self.memories.user_id),
                "failed_count": len(active_pending),
                "index_sync_pending": True,
            },
        )
        raise MemoryIndexOutOfSyncError

    async def _search_neighbors(
        self,
        companion_id: UUID,
        remaining: list[tuple[int, MemoryCandidate]],
    ) -> list[Memory]:
        neighbor_ids: list[UUID] = []
        seen: set[UUID] = set()
        for _index, candidate in remaining:
            vector = await self.embeddings.embed(candidate.content)
            matches = await self.vector_index.search(
                query=vector,
                user_id=self.memories.user_id,
                companion_id=companion_id,
                top_k=self.top_k,
                score_threshold=self.score_threshold,
            )
            for match in matches:
                if match.memory_id in seen:
                    continue
                seen.add(match.memory_id)
                neighbor_ids.append(match.memory_id)
        return await self.memories.get_active_by_ids(companion_id, neighbor_ids)

    async def _classify(
        self,
        remaining: list[tuple[int, MemoryCandidate]],
        neighbors: list[Memory],
    ) -> dict[int, MemoryReconciliationDecision]:
        index_map = {
            llm_index: original for llm_index, (original, _candidate) in enumerate(remaining)
        }
        payload = {
            "candidates": [
                {
                    "candidate_index": llm_index,
                    "type": candidate.type.value,
                    "content": candidate.content,
                    "importance": float(candidate.importance),
                    "confidence": float(candidate.confidence),
                }
                for llm_index, (_original, candidate) in enumerate(remaining)
            ],
            "existing_memories": [
                {
                    "id": str(memory.id),
                    "type": memory.type.value,
                    "content": memory.content,
                    "importance": float(memory.importance),
                    "confidence": float(memory.confidence),
                }
                for memory in neighbors
            ],
        }
        try:
            raw = await self.llm_provider.generate_response(
                [
                    LLMMessage(role="system", content=RECONCILIATION_SYSTEM_PROMPT),
                    LLMMessage(role="user", content=json.dumps(payload, ensure_ascii=False)),
                ]
            )
        except LLMProviderError:
            logger.warning(
                "memory_reconciliation_llm_failed",
                extra={
                    "user_id": str(self.memories.user_id),
                    "candidate_count": len(remaining),
                },
                exc_info=True,
            )
            raise
        parsed = _parse_reconciliation_result(raw, expected_count=len(remaining))
        allowed_ids = {memory.id for memory in neighbors}
        expected_indices = set(range(len(remaining)))
        validated = _validate_decisions(parsed.decisions, expected_indices, allowed_ids)
        return {
            index_map[llm_index]: MemoryReconciliationDecision(
                candidate_index=index_map[llm_index],
                relation=decision.relation,
                existing_memory_id=decision.existing_memory_id,
            )
            for llm_index, decision in validated.items()
        }

    async def _apply(
        self,
        companion_id: UUID,
        candidates: Sequence[MemoryCandidate],
        decisions: dict[int, MemoryReconciliationDecision],
        *,
        source_conversation_id: UUID | None,
    ) -> list[Memory]:
        if set(decisions) != set(range(len(candidates))):
            raise MemoryReconciliationError
        referenced_ids = [
            decision.existing_memory_id
            for decision in decisions.values()
            if decision.existing_memory_id is not None
        ]
        existing = await self.memories.get_active_by_ids(companion_id, referenced_ids)
        existing_by_id = {memory.id: memory for memory in existing}
        if set(referenced_ids) - set(existing_by_id):
            raise MemoryReconciliationError

        created_by_index: dict[int, Memory] = {}
        to_deactivate: list[tuple[Memory, DeactivationReason, int]] = []
        creating_relations = {
            MemoryRelation.ADDITIONAL,
            MemoryRelation.UNRELATED,
            MemoryRelation.UPDATE,
            MemoryRelation.CONTRADICTION,
        }
        for index in range(len(candidates)):
            decision = decisions[index]
            if decision.relation in creating_relations:
                created = await self.memories.create(
                    companion_id,
                    candidates[index].to_memory_create(),
                    source_conversation_id=source_conversation_id,
                )
                created_by_index[index] = created
                if decision.relation in {MemoryRelation.UPDATE, MemoryRelation.CONTRADICTION}:
                    existing_id = decision.existing_memory_id
                    if existing_id is None:
                        raise MemoryReconciliationError
                    reason = (
                        DeactivationReason.UPDATED
                        if decision.relation is MemoryRelation.UPDATE
                        else DeactivationReason.CONTRADICTED
                    )
                    to_deactivate.append((existing_by_id[existing_id], reason, index))
                    logger.info(
                        "memory_reconciliation_replaced",
                        extra={
                            "companion_id": str(companion_id),
                            "user_id": str(self.memories.user_id),
                            "candidate_index": index,
                            "relation": decision.relation.value,
                            "existing_memory_id": str(decision.existing_memory_id),
                            "action": "replace",
                        },
                    )
                else:
                    logger.info(
                        "memory_reconciliation_created",
                        extra={
                            "companion_id": str(companion_id),
                            "user_id": str(self.memories.user_id),
                            "candidate_index": index,
                            "relation": decision.relation.value,
                            "action": "create",
                        },
                    )
            elif decision.relation is MemoryRelation.DISCARD:
                logger.info(
                    "memory_reconciliation_discarded",
                    extra={
                        "companion_id": str(companion_id),
                        "user_id": str(self.memories.user_id),
                        "candidate_index": index,
                        "relation": decision.relation.value,
                        "action": "discard",
                    },
                )

        now = datetime.now(UTC)
        for old, reason, new_index in to_deactivate:
            self.memories.mark_deactivated(
                old,
                reason=reason,
                at=now,
                superseded_by=created_by_index[new_index],
            )

        await self.memories.uow.commit()
        touched = [*created_by_index.values(), *[old for old, _reason, _index in to_deactivate]]
        for memory in touched:
            await self.memories.uow.refresh(memory)
        for memory in touched:
            await project_and_clear_pending(self.indexing, memory, self.memories.uow)
        return [created_by_index[index] for index in sorted(created_by_index)]


def _parse_reconciliation_result(raw: str, *, expected_count: int) -> MemoryReconciliationResult:
    try:
        payload = json.loads(raw)
        result = MemoryReconciliationResult.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning(
            "memory_reconciliation_invalid_output",
            extra={
                "error_type": type(exc).__name__,
                "candidate_count": expected_count,
            },
        )
        raise MemoryReconciliationError from exc
    return result


def _validate_decisions(
    decisions: list[MemoryReconciliationDecision],
    expected_indices: set[int],
    allowed_ids: set[UUID],
) -> dict[int, MemoryReconciliationDecision]:
    indices = [decision.candidate_index for decision in decisions]
    if len(indices) != len(expected_indices) or set(indices) != expected_indices:
        raise MemoryReconciliationError
    superseded: set[UUID] = set()
    duplicated: set[UUID] = set()
    by_index: dict[int, MemoryReconciliationDecision] = {}
    for decision in decisions:
        existing_id = decision.existing_memory_id
        if existing_id is not None and existing_id not in allowed_ids:
            raise MemoryReconciliationError
        if decision.relation in {MemoryRelation.UPDATE, MemoryRelation.CONTRADICTION}:
            if existing_id is None or existing_id in superseded or existing_id in duplicated:
                raise MemoryReconciliationError
            superseded.add(existing_id)
        elif decision.relation is MemoryRelation.DUPLICATE:
            if existing_id is None or existing_id in superseded:
                raise MemoryReconciliationError
            duplicated.add(existing_id)
        by_index[decision.candidate_index] = decision
    return by_index
