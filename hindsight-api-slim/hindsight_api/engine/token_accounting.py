"""Token accounting for Precision-per-Token tracking.

Records per-operation token usage (retain/recall/reflect) to the token_usage
table. All writes are fire-and-forget async to avoid adding latency to the
critical path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import tiktoken

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)

_encoding = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count tokens in a text string using cl100k_base encoding."""
    if not text:
        return 0
    return len(_encoding.encode(text, disallowed_special=()))


@dataclass
class TokenUsageRecord:
    """A single token usage measurement."""

    bank_id: str
    operation: str  # "retain" | "recall" | "reflect"
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    context_tokens: int = 0
    query_tier: str | None = None
    candidate_count: int | None = None
    novelty_rejected: int | None = None
    baseline_tokens: int | None = None
    saved_tokens: int | None = None


async def record_token_usage(pool: asyncpg.Pool, record: TokenUsageRecord) -> None:
    """Write a token usage record to the database.

    Fire-and-forget: exceptions are logged but never raised, so this
    never blocks or fails the parent operation.
    """
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO token_usage (
                    bank_id, operation, created_at,
                    llm_input_tokens, llm_output_tokens, context_tokens,
                    query_tier, candidate_count, novelty_rejected,
                    baseline_tokens, saved_tokens
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                record.bank_id,
                record.operation,
                datetime.now(timezone.utc),
                record.llm_input_tokens,
                record.llm_output_tokens,
                record.context_tokens,
                record.query_tier,
                record.candidate_count,
                record.novelty_rejected,
                record.baseline_tokens,
                record.saved_tokens,
            )
    except Exception:
        logger.warning("Failed to record token usage", exc_info=True)


@dataclass
class RecallTokenStats:
    """Computed from a recall result for accounting purposes."""

    context_tokens: int = 0
    num_results: int = 0
    baseline_tokens: int = 0

    @property
    def saved_tokens(self) -> int:
        return max(0, self.baseline_tokens - self.context_tokens)


def measure_recall_tokens(result_dicts: list[dict]) -> RecallTokenStats:
    """Measure token stats from recall result dicts (the final filtered results).

    context_tokens = sum of tokens in each result's 'text' field.
    This is exactly what the agent receives and pays for.
    """
    total = 0
    for r in result_dicts:
        text = r.get("text", "")
        if text:
            total += len(_encoding.encode(text, disallowed_special=()))

    return RecallTokenStats(
        context_tokens=total,
        num_results=len(result_dicts),
        baseline_tokens=total,  # Will be overridden when tier routing is active
    )
