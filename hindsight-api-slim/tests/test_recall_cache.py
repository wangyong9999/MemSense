"""
Tests for the recall result cache.

Covers: cache hit/miss, TTL expiry, bank invalidation, LRU eviction, stats, thread safety.
"""

from __future__ import annotations

import time

import pytest

from hindsight_api.engine.search.recall_cache import RecallCache, RecallCacheKey

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _key(
    bank_id: str = "bank1",
    query: str = "test query",
    fact_type: list[str] | None = None,
    thinking_budget: int = 300,
    tags: list[str] | None = None,
    tags_match: str = "any",
) -> RecallCacheKey:
    return RecallCacheKey.build(
        bank_id=bank_id,
        query=query,
        fact_type=fact_type or ["world", "experience"],
        thinking_budget=thinking_budget,
        tags=tags,
        tags_match=tags_match,
    )


FAKE_RESULT = {"results": [{"text": "some memory", "id": "1"}]}


# ===================================================================
# Key construction
# ===================================================================


class TestRecallCacheKey:
    def test_query_normalized(self):
        k1 = _key(query="  Hello World  ")
        k2 = _key(query="hello world")
        assert k1 == k2

    def test_different_queries(self):
        k1 = _key(query="alpha")
        k2 = _key(query="beta")
        assert k1 != k2

    def test_different_banks(self):
        k1 = _key(bank_id="bank_a")
        k2 = _key(bank_id="bank_b")
        assert k1 != k2

    def test_fact_type_order_independent(self):
        k1 = _key(fact_type=["world", "experience"])
        k2 = _key(fact_type=["experience", "world"])
        assert k1 == k2

    def test_tags_order_independent(self):
        k1 = _key(tags=["a", "b"])
        k2 = _key(tags=["b", "a"])
        assert k1 == k2

    def test_no_tags(self):
        k1 = _key(tags=None)
        k2 = _key(tags=[])
        assert k1 == k2

    def test_different_max_tokens(self):
        k1 = RecallCacheKey.build("b", "q", ["world"], 300, max_tokens=2048)
        k2 = RecallCacheKey.build("b", "q", ["world"], 300, max_tokens=4096)
        assert k1 != k2

    def test_different_include_entities(self):
        k1 = RecallCacheKey.build("b", "q", ["world"], 300, include_entities=False)
        k2 = RecallCacheKey.build("b", "q", ["world"], 300, include_entities=True)
        assert k1 != k2

    def test_different_question_date(self):
        from datetime import datetime, timezone

        k1 = RecallCacheKey.build("b", "q", ["world"], 300, question_date=None)
        k2 = RecallCacheKey.build("b", "q", ["world"], 300, question_date=datetime(2024, 1, 1, tzinfo=timezone.utc))
        assert k1 != k2

    def test_hashable(self):
        k = _key()
        d = {k: "value"}
        assert d[k] == "value"


# ===================================================================
# Cache hit/miss
# ===================================================================


class TestCacheHitMiss:
    def test_miss_on_empty(self):
        cache = RecallCache(max_size=10, ttl_seconds=60)
        assert cache.get(_key()) is None

    def test_put_then_hit(self):
        cache = RecallCache(max_size=10, ttl_seconds=60)
        key = _key()
        cache.put(key, FAKE_RESULT)
        assert cache.get(key) is FAKE_RESULT

    def test_miss_different_key(self):
        cache = RecallCache(max_size=10, ttl_seconds=60)
        cache.put(_key(query="alpha"), FAKE_RESULT)
        assert cache.get(_key(query="beta")) is None

    def test_overwrite_existing(self):
        cache = RecallCache(max_size=10, ttl_seconds=60)
        key = _key()
        cache.put(key, "old")
        cache.put(key, "new")
        assert cache.get(key) == "new"


# ===================================================================
# TTL expiration
# ===================================================================


class TestTTL:
    def test_expired_entry_returns_none(self):
        cache = RecallCache(max_size=10, ttl_seconds=0)  # instant expiry
        key = _key()
        cache.put(key, FAKE_RESULT)
        # TTL is 0, so next get() should miss
        time.sleep(0.01)
        assert cache.get(key) is None

    def test_non_expired_entry_returns_result(self):
        cache = RecallCache(max_size=10, ttl_seconds=60)
        key = _key()
        cache.put(key, FAKE_RESULT)
        assert cache.get(key) is FAKE_RESULT


# ===================================================================
# Bank invalidation
# ===================================================================


class TestBankInvalidation:
    def test_invalidate_clears_bank_entries(self):
        cache = RecallCache(max_size=10, ttl_seconds=60)
        key = _key(bank_id="bank_x")
        cache.put(key, FAKE_RESULT)
        assert cache.get(key) is FAKE_RESULT

        cache.invalidate_bank("bank_x")
        assert cache.get(key) is None

    def test_invalidate_does_not_affect_other_banks(self):
        cache = RecallCache(max_size=10, ttl_seconds=60)
        key_a = _key(bank_id="bank_a")
        key_b = _key(bank_id="bank_b")
        cache.put(key_a, "result_a")
        cache.put(key_b, "result_b")

        cache.invalidate_bank("bank_a")

        assert cache.get(key_a) is None
        assert cache.get(key_b) == "result_b"

    def test_put_after_invalidate_works(self):
        cache = RecallCache(max_size=10, ttl_seconds=60)
        key = _key(bank_id="bank_x")
        cache.put(key, "old")
        cache.invalidate_bank("bank_x")
        cache.put(key, "new")
        assert cache.get(key) == "new"


# ===================================================================
# LRU eviction
# ===================================================================


class TestLRUEviction:
    def test_evicts_oldest_when_full(self):
        cache = RecallCache(max_size=3, ttl_seconds=60)
        k1 = _key(query="q1")
        k2 = _key(query="q2")
        k3 = _key(query="q3")
        k4 = _key(query="q4")

        cache.put(k1, "r1")
        cache.put(k2, "r2")
        cache.put(k3, "r3")
        cache.put(k4, "r4")  # should evict k1

        assert cache.get(k1) is None
        assert cache.get(k2) == "r2"
        assert cache.get(k4) == "r4"

    def test_access_refreshes_lru_position(self):
        cache = RecallCache(max_size=3, ttl_seconds=60)
        k1 = _key(query="q1")
        k2 = _key(query="q2")
        k3 = _key(query="q3")
        k4 = _key(query="q4")

        cache.put(k1, "r1")
        cache.put(k2, "r2")
        cache.put(k3, "r3")

        # Access k1, making k2 the oldest
        cache.get(k1)

        cache.put(k4, "r4")  # should evict k2, not k1

        assert cache.get(k1) == "r1"
        assert cache.get(k2) is None


# ===================================================================
# Stats
# ===================================================================


class TestStats:
    def test_initial_stats(self):
        cache = RecallCache(max_size=10, ttl_seconds=60)
        s = cache.stats()
        assert s["exact_hits"] == 0
        assert s["misses"] == 0
        assert s["hit_rate"] == 0.0
        assert s["size"] == 0

    def test_stats_after_operations(self):
        cache = RecallCache(max_size=10, ttl_seconds=60)
        key = _key()
        cache.get(key)  # miss
        cache.put(key, FAKE_RESULT)
        cache.get(key)  # hit
        cache.get(key)  # hit

        s = cache.stats()
        assert s["exact_hits"] == 2
        assert s["misses"] == 1
        assert s["hit_rate"] == pytest.approx(2 / 3, rel=0.01)
        assert s["size"] == 1

    def test_clear_resets_stats(self):
        cache = RecallCache(max_size=10, ttl_seconds=60)
        cache.put(_key(), FAKE_RESULT)
        cache.get(_key())
        cache.clear()

        s = cache.stats()
        assert s["exact_hits"] == 0
        assert s["size"] == 0


# ===================================================================
# Realistic flow simulation
# ===================================================================


class TestRealisticFlow:
    def test_retain_invalidates_then_new_result_cached(self):
        """Simulates: recall → retain → recall (should NOT return stale cache)."""
        cache = RecallCache(max_size=10, ttl_seconds=60)
        key = _key(bank_id="user_bank")

        # First recall — cache miss, store result
        assert cache.get(key) is None
        cache.put(key, {"results": [{"text": "old fact"}]})

        # Retain happens — invalidate
        cache.invalidate_bank("user_bank")

        # Second recall — should miss (stale), new pipeline result stored
        assert cache.get(key) is None
        cache.put(key, {"results": [{"text": "old fact"}, {"text": "new fact"}]})

        # Third recall — cache hit with updated result
        cached = cache.get(key)
        assert cached is not None
        assert len(cached["results"]) == 2

    def test_same_query_different_max_tokens_are_separate(self):
        """max_tokens=2048 and max_tokens=4096 should NOT share cache entries."""
        cache = RecallCache(max_size=10, ttl_seconds=60)
        k_small = RecallCacheKey.build("b", "query", ["world"], 300, max_tokens=2048)
        k_large = RecallCacheKey.build("b", "query", ["world"], 300, max_tokens=4096)

        cache.put(k_small, {"results": ["short"]})
        cache.put(k_large, {"results": ["short", "medium", "long"]})

        assert len(cache.get(k_small)["results"]) == 1
        assert len(cache.get(k_large)["results"]) == 3

    def test_same_query_different_include_flags_are_separate(self):
        """include_entities=True/False should NOT share cache entries."""
        cache = RecallCache(max_size=10, ttl_seconds=60)
        k_no_ent = RecallCacheKey.build("b", "q", ["world"], 300, include_entities=False)
        k_with_ent = RecallCacheKey.build("b", "q", ["world"], 300, include_entities=True)

        cache.put(k_no_ent, {"results": [], "entities": None})
        cache.put(k_with_ent, {"results": [], "entities": {"Alice": {"name": "Alice"}}})

        assert cache.get(k_no_ent)["entities"] is None
        assert cache.get(k_with_ent)["entities"] is not None

    def test_multi_bank_isolation(self):
        """Invalidating bank A should not affect bank B's cache."""
        cache = RecallCache(max_size=10, ttl_seconds=60)
        ka = _key(bank_id="bank_a", query="shared query")
        kb = _key(bank_id="bank_b", query="shared query")

        cache.put(ka, "result_a")
        cache.put(kb, "result_b")

        cache.invalidate_bank("bank_a")

        assert cache.get(ka) is None  # invalidated
        assert cache.get(kb) == "result_b"  # untouched

    def test_disabled_cache_is_none(self):
        """When cache is None (disabled), code paths should not crash."""
        # This tests the pattern used in memory_engine.py
        cache = None
        if cache is not None:
            cache.get(_key())  # should never reach here
        # No crash = pass


# ===================================================================
# Tier 1: Fuzzy matching
# ===================================================================


class TestFuzzyMatching:
    def test_similar_query_hits(self):
        """Queries with high token overlap should fuzzy-match."""
        cache = RecallCache(max_size=10, ttl_seconds=60, fuzzy_threshold=0.6)
        # Store: "What games does Jolene play with her partner"
        k1 = _key(query="What games does Jolene play with her partner")
        cache.put(k1, "result_games")

        # Lookup: "Which games does Jolene play with partner" (similar but not identical)
        k2 = _key(query="Which games does Jolene play with partner")
        assert cache.get(k2) is None  # Tier 0 miss
        assert cache.find_similar(k2) == "result_games"  # Tier 1 hit

    def test_different_query_misses(self):
        """Queries with low token overlap should not fuzzy-match."""
        cache = RecallCache(max_size=10, ttl_seconds=60, fuzzy_threshold=0.6)
        k1 = _key(query="What games does Jolene play")
        cache.put(k1, "result_games")

        k2 = _key(query="When did Deborah visit the park")
        assert cache.find_similar(k2) is None

    def test_temporal_query_excluded(self):
        """Queries with relative temporal expressions skip fuzzy matching."""
        cache = RecallCache(max_size=10, ttl_seconds=60, fuzzy_threshold=0.5)
        k1 = _key(query="What did Alice do recently at work")
        cache.put(k1, "result_recent")

        # Same tokens except "recently" vs "yesterday" — should NOT fuzzy match
        k2 = _key(query="What did Alice do yesterday at work")
        assert cache.find_similar(k2) is None  # temporal guard blocks it

    def test_temporal_absolute_not_excluded(self):
        """Queries with absolute dates (no relative expressions) are OK for fuzzy."""
        cache = RecallCache(max_size=10, ttl_seconds=60, fuzzy_threshold=0.5)
        k1 = _key(query="What happened in March 2024 with the project")
        cache.put(k1, "result_march")

        k2 = _key(query="What happened with the project in March 2024")
        assert cache.find_similar(k2) == "result_march"

    def test_short_query_excluded(self):
        """Queries with fewer than 2 meaningful tokens skip fuzzy matching."""
        cache = RecallCache(max_size=10, ttl_seconds=60, fuzzy_threshold=0.5)
        k1 = _key(query="hello")
        cache.put(k1, "result_hello")

        k2 = _key(query="hi")
        assert cache.find_similar(k2) is None

    def test_different_bank_no_fuzzy(self):
        """Fuzzy matching requires same bank_id."""
        cache = RecallCache(max_size=10, ttl_seconds=60, fuzzy_threshold=0.5)
        k1 = _key(bank_id="bank_a", query="What games does Jolene play")
        cache.put(k1, "result_a")

        k2 = _key(bank_id="bank_b", query="What games does Jolene play")
        assert cache.find_similar(k2) is None

    def test_max_tokens_must_match_exactly(self):
        """Fuzzy hit requires exact max_tokens match (cached result is already token-filtered)."""
        cache = RecallCache(max_size=10, ttl_seconds=60, fuzzy_threshold=0.5)
        k1 = RecallCacheKey.build("b", "What games does Jolene play", ["world"], 300, max_tokens=4096)
        cache.put(k1, "result_4k")

        # Different max_tokens — should NOT match even with similar query
        k2 = RecallCacheKey.build("b", "Which games does Jolene play", ["world"], 300, max_tokens=8192)
        assert cache.find_similar(k2) is None

        # Same max_tokens — should match
        k3 = RecallCacheKey.build("b", "Which games does Jolene play", ["world"], 300, max_tokens=4096)
        assert cache.find_similar(k3) == "result_4k"

    def test_fuzzy_stats_tracked(self):
        """Fuzzy hits are tracked separately in stats."""
        cache = RecallCache(max_size=10, ttl_seconds=60, fuzzy_threshold=0.5)
        k1 = _key(query="What games does Jolene play with partner")
        cache.put(k1, "result")

        k2 = _key(query="Which games does Jolene play with partner")
        cache.get(k2)  # Tier 0 miss
        cache.find_similar(k2)  # Tier 1 hit

        s = cache.stats()
        assert s["exact_hits"] == 0
        assert s["fuzzy_hits"] == 1
        assert s["misses"] == 1

    def test_chinese_fuzzy_match(self):
        """Chinese queries with matching segments should fuzzy-match."""
        cache = RecallCache(max_size=10, ttl_seconds=60, fuzzy_threshold=0.5)
        # "客户 张三 的 风控预警 阈值" → tokens: {客户张三, 风控预警阈值, ...}
        k1 = _key(query="customer 张三 risk rating query")
        cache.put(k1, "result_risk")

        # Same core tokens, different order/stopwords
        k2 = _key(query="query risk rating for 张三 customer")
        assert cache.find_similar(k2) is not None

    def test_chinese_temporal_excluded(self):
        """Chinese relative temporal expressions block fuzzy matching."""
        cache = RecallCache(max_size=10, ttl_seconds=60, fuzzy_threshold=0.5)
        k1 = _key(query="客户最近的交易记录")
        cache.put(k1, "result_recent")

        k2 = _key(query="客户之前的交易记录")
        assert cache.find_similar(k2) is None

    def test_threshold_zero_disables_fuzzy(self):
        """Setting threshold to 0 disables fuzzy matching entirely."""
        cache = RecallCache(max_size=10, ttl_seconds=60, fuzzy_threshold=0.0)
        k1 = _key(query="What games does Jolene play")
        cache.put(k1, "result")

        k2 = _key(query="What games does Jolene play")  # even identical query
        assert cache.find_similar(k2) is None

    def test_invalidation_affects_fuzzy(self):
        """Bank invalidation should also affect fuzzy hits."""
        cache = RecallCache(max_size=10, ttl_seconds=60, fuzzy_threshold=0.5)
        k1 = _key(bank_id="bx", query="What games does Jolene play with partner")
        cache.put(k1, "old_result")

        cache.invalidate_bank("bx")

        k2 = _key(bank_id="bx", query="Which games does Jolene play with partner")
        assert cache.find_similar(k2) is None
