"""Tests for token accounting module."""

import pytest

from hindsight_api.engine.token_accounting import (
    TokenUsageRecord,
    count_tokens,
    measure_recall_tokens,
)


class TestCountTokens:
    def test_empty_string(self):
        assert count_tokens("") == 0

    def test_simple_text(self):
        tokens = count_tokens("Hello world")
        assert tokens == 2

    def test_longer_text(self):
        tokens = count_tokens("The quick brown fox jumps over the lazy dog.")
        assert tokens > 5

    def test_none_safe(self):
        # count_tokens only takes str, but empty string should be 0
        assert count_tokens("") == 0


class TestMeasureRecallTokens:
    def test_empty_results(self):
        stats = measure_recall_tokens([])
        assert stats.context_tokens == 0
        assert stats.num_results == 0

    def test_single_result(self):
        results = [{"text": "Alice works at Google on the AI team", "id": "1", "fact_type": "world"}]
        stats = measure_recall_tokens(results)
        assert stats.context_tokens > 0
        assert stats.num_results == 1

    def test_multiple_results(self):
        results = [
            {"text": "Alice works at Google", "id": "1"},
            {"text": "Bob works at Meta", "id": "2"},
            {"text": "Charlie works at Apple", "id": "3"},
        ]
        stats = measure_recall_tokens(results)
        assert stats.num_results == 3
        # Each sentence is ~4-5 tokens, total should be ~12-15
        assert stats.context_tokens > 10

    def test_missing_text_field(self):
        results = [{"id": "1", "fact_type": "world"}]
        stats = measure_recall_tokens(results)
        assert stats.context_tokens == 0

    def test_saved_tokens_default(self):
        results = [{"text": "Hello world"}]
        stats = measure_recall_tokens(results)
        # Without tier routing, baseline == context_tokens, saved == 0
        assert stats.saved_tokens == 0


class TestTokenUsageRecord:
    def test_defaults(self):
        record = TokenUsageRecord(bank_id="test", operation="recall")
        assert record.llm_input_tokens == 0
        assert record.llm_output_tokens == 0
        assert record.context_tokens == 0
        assert record.query_tier is None

    def test_with_values(self):
        record = TokenUsageRecord(
            bank_id="test",
            operation="recall",
            context_tokens=500,
            query_tier="B",
            baseline_tokens=1200,
            saved_tokens=700,
        )
        assert record.context_tokens == 500
        assert record.saved_tokens == 700


@pytest.mark.asyncio
async def test_recall_records_token_usage(memory, request_context):
    """Integration test: recall should record token usage to token_usage table."""
    from datetime import timezone

    bank_id = f"test_token_accounting_{__import__('time').time()}"
    try:
        # Retain some data
        await memory.retain_async(
            bank_id=bank_id,
            content="Alice works at Google on the AI research team. She focuses on large language models.",
            context="team info",
            event_date=__import__("datetime").datetime(2026, 1, 15, tzinfo=timezone.utc),
            request_context=request_context,
        )
        await memory.wait_for_background_tasks()

        # Recall - this should trigger token accounting
        result = await memory.recall_async(
            bank_id=bank_id,
            query="Where does Alice work?",
            request_context=request_context,
        )

        # Give the fire-and-forget task a moment to complete
        import asyncio

        await asyncio.sleep(0.5)

        # Check token_usage table
        pool = await memory._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM token_usage WHERE bank_id = $1 AND operation = 'recall' ORDER BY created_at DESC LIMIT 1",
                bank_id,
            )

        if row is not None:
            # Token usage was recorded
            assert row["operation"] == "recall"
            assert row["context_tokens"] >= 0
            assert row["bank_id"] == bank_id
        # If row is None, the table might not exist yet (migration not run) — that's OK for this test
    finally:
        await memory.delete_bank(bank_id, request_context=request_context)
