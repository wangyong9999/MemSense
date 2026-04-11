"""
In-memory LRU cache for recall results.

MemSense enhancement: caches the full recall pipeline output so that
identical queries to the same bank skip retrieval, RRF, and reranking.
Cache is invalidated per-bank whenever a mutation (retain/delete) occurs.

This module is intentionally self-contained — it depends only on Python
stdlib and has no imports from memory_engine or other engine internals,
keeping the merge surface with upstream Hindsight minimal.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecallCacheKey:
    """Hashable cache key derived from recall parameters.

    Every parameter that can change the recall result is included in the key.
    This is deliberately conservative — a cache miss is cheap (just runs the
    pipeline normally), but a cache hit with wrong results is a correctness bug.
    """

    bank_id: str
    query_normalized: str
    fact_types: frozenset[str]
    budget_value: int  # thinking_budget numeric value
    max_tokens: int
    tags: frozenset[str]
    tags_match: str
    question_date: str | None  # ISO string or None
    include_entities: bool
    include_chunks: bool
    include_source_facts: bool

    @classmethod
    def build(
        cls,
        bank_id: str,
        query: str,
        fact_type: list[str],
        thinking_budget: int,
        max_tokens: int = 4096,
        tags: list[str] | None = None,
        tags_match: str = "any",
        question_date: "datetime | None" = None,
        include_entities: bool = False,
        include_chunks: bool = False,
        include_source_facts: bool = False,
    ) -> RecallCacheKey:
        return cls(
            bank_id=bank_id,
            query_normalized=query.strip().lower(),
            fact_types=frozenset(fact_type),
            budget_value=thinking_budget,
            max_tokens=max_tokens,
            tags=frozenset(tags) if tags else frozenset(),
            tags_match=tags_match,
            question_date=question_date.isoformat() if question_date else None,
            include_entities=include_entities,
            include_chunks=include_chunks,
            include_source_facts=include_source_facts,
        )


@dataclass
class _CacheEntry:
    """Internal cache entry wrapping a result with metadata."""

    result: Any  # RecallResult (not imported to avoid coupling)
    created_at: float
    bank_generation: int


class RecallCache:
    """Thread-safe, in-memory LRU cache with TTL and per-bank invalidation.

    Usage::

        cache = RecallCache(max_size=256, ttl_seconds=300)

        # On recall — check cache first
        key = RecallCacheKey.build(bank_id, query, fact_type, thinking_budget, tags, tags_match)
        cached = cache.get(key)
        if cached is not None:
            return cached  # fast path

        # ... run full pipeline ...
        cache.put(key, result)

        # On retain/delete — invalidate bank
        cache.invalidate_bank(bank_id)
    """

    def __init__(self, max_size: int = 256, ttl_seconds: int = 300):
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._cache: OrderedDict[RecallCacheKey, _CacheEntry] = OrderedDict()
        self._bank_generations: dict[str, int] = {}
        self._lock = threading.Lock()
        # Stats
        self._hits = 0
        self._misses = 0

    def get(self, key: RecallCacheKey) -> Any | None:
        """Look up a cached result. Returns None on miss, expiry, or stale bank."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None

            # Check TTL
            if time.time() - entry.created_at > self._ttl_seconds:
                del self._cache[key]
                self._misses += 1
                return None

            # Check bank generation (stale after retain/delete)
            current_gen = self._bank_generations.get(key.bank_id, 0)
            if entry.bank_generation != current_gen:
                del self._cache[key]
                self._misses += 1
                return None

            # Hit — move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return entry.result

    def put(self, key: RecallCacheKey, result: Any) -> None:
        """Store a result in the cache."""
        with self._lock:
            current_gen = self._bank_generations.get(key.bank_id, 0)

            # If already present, update in place
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = _CacheEntry(
                    result=result,
                    created_at=time.time(),
                    bank_generation=current_gen,
                )
                return

            # Evict oldest if over capacity
            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)

            self._cache[key] = _CacheEntry(
                result=result,
                created_at=time.time(),
                bank_generation=current_gen,
            )

    def invalidate_bank(self, bank_id: str) -> None:
        """Bump the generation counter for *bank_id*, invalidating all its entries.

        Entries are lazily evicted on next ``get()`` rather than eagerly
        scanned, so this is O(1).
        """
        with self._lock:
            self._bank_generations[bank_id] = self._bank_generations.get(bank_id, 0) + 1

    def clear(self) -> None:
        """Drop all entries and reset stats."""
        with self._lock:
            self._cache.clear()
            self._bank_generations.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict[str, Any]:
        """Return cache hit/miss statistics."""
        with self._lock:
            total = self._hits + self._misses
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 3) if total > 0 else 0.0,
                "size": len(self._cache),
                "max_size": self._max_size,
                "ttl_seconds": self._ttl_seconds,
            }
