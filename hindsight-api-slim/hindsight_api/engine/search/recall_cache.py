"""
In-memory LRU cache for recall results with fuzzy matching.

MemSense enhancement: caches the full recall pipeline output so that
identical or similar queries to the same bank skip retrieval, RRF, and
reranking.

Two tiers:
  - Tier 0: exact key match (~0ms, zero risk)
  - Tier 1: fuzzy Jaccard match on query tokens (~0.1ms, guarded by
    temporal expression exclusion and minimum token threshold)

Cache is invalidated per-bank whenever a mutation (retain/delete) occurs
via a lightweight generation counter (O(1) bump, lazy eviction).

This module is intentionally self-contained — it depends only on Python
stdlib and has no imports from memory_engine or other engine internals,
keeping the merge surface with upstream Hindsight minimal.

Design informed by tiered retrieval strategies in agent memory systems.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lightweight tokenizer for fuzzy similarity (no external dependencies)
# ---------------------------------------------------------------------------

_EN_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "shall",
        "can",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "about",
        "between",
        "through",
        "after",
        "before",
        "during",
        "and",
        "but",
        "or",
        "not",
        "so",
        "if",
        "than",
        "that",
        "this",
        "it",
        "its",
        "i",
        "me",
        "my",
        "we",
        "our",
        "you",
        "your",
        "he",
        "him",
        "his",
        "she",
        "her",
        "they",
        "them",
        "their",
        "what",
        "which",
        "who",
        "whom",
        "when",
        "where",
        "how",
        "why",
        "all",
        "each",
        "any",
        "some",
        "no",
        "just",
        "also",
        "very",
        "much",
        "more",
        "most",
        "only",
        "other",
    }
)

_ZH_STOPCHARS: frozenset[str] = frozenset(
    "的了在是我有和就不人都一上也很到说要去你会着看好这他她它们那些被把让吗吧呢啊哦嗯么呀哪"
)

# Relative temporal expressions that make query results time-dependent.
# Absolute dates ("March 2024", "2024-03-15") are safe — same result anytime.
_TEMPORAL_RE = re.compile(
    r"(?i)\b(recently|lately|today|tonight|yesterday|tomorrow|last\s+\w+|next\s+\w+|this\s+\w+|ago|just\s+now)\b"
    r"|最近|刚才|昨天|今天|明天|前天|上周|下周|上个月|下个月|去年|今年|明年",
)

_SPLIT_RE = re.compile(r"[\s,;:!?\.\-—–/|()（）【】「」《》]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")


def _tokenize_query(text: str) -> frozenset[str]:
    """Extract meaningful tokens for Jaccard similarity.

    Tokenize for similarity: lowercase, split, remove stopwords,
    filter short tokens. Extended with Chinese support.
    """
    text = text.strip().lower()
    parts = _SPLIT_RE.split(text)
    tokens: set[str] = set()

    for part in parts:
        if not part:
            continue
        # CJK: split on single-char stopwords, keep segments ≥ 2 chars
        cjk_spans = _CJK_RE.findall(part)
        for span in cjk_spans:
            seg: list[str] = []
            for ch in span:
                if ch in _ZH_STOPCHARS:
                    if len(seg) >= 2:
                        tokens.add("".join(seg))
                    seg = []
                else:
                    seg.append(ch)
            if len(seg) >= 2:
                tokens.add("".join(seg))
        # Latin: filter stopwords and short tokens
        latin = _CJK_RE.sub(" ", part).strip()
        for word in latin.split():
            if len(word) >= 2 and word not in _EN_STOPWORDS:
                tokens.add(word)

    return frozenset(tokens)


def _has_relative_temporal(text: str) -> bool:
    """Detect relative temporal expressions that make results time-dependent."""
    return bool(_TEMPORAL_RE.search(text))


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard similarity between two token sets. Returns 0.0–1.0."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union > 0 else 0.0


# ---------------------------------------------------------------------------
# Cache key and entry
# ---------------------------------------------------------------------------


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

    def _params_match(self, other: RecallCacheKey) -> bool:
        """Check if all non-query parameters match exactly.

        Used by Tier 1 fuzzy matching: query text is compared via Jaccard,
        but all other parameters must be identical.
        """
        return (
            self.bank_id == other.bank_id
            and self.fact_types == other.fact_types
            and self.budget_value == other.budget_value
            and self.tags == other.tags
            and self.tags_match == other.tags_match
            and self.question_date == other.question_date
            and self.include_entities == other.include_entities
            and self.include_chunks == other.include_chunks
            and self.include_source_facts == other.include_source_facts
            # max_tokens: exact match required — cached result is already
            # token-filtered, so a larger/smaller budget would be wrong
            and self.max_tokens == other.max_tokens
        )


@dataclass
class _CacheEntry:
    """Internal cache entry wrapping a result with metadata."""

    result: Any  # RecallResult (not imported to avoid coupling)
    created_at: float
    bank_generation: int
    query_tokens: frozenset[str]  # pre-computed for Tier 1 fuzzy matching


# ---------------------------------------------------------------------------
# RecallCache
# ---------------------------------------------------------------------------


class RecallCache:
    """Thread-safe, in-memory LRU cache with TTL, per-bank invalidation,
    and Tier 1 fuzzy matching.

    Tier 0 (exact):
        Lookup by full RecallCacheKey hash. ~0ms, zero risk.

    Tier 1 (fuzzy):
        On Tier 0 miss, scan same-bank entries for Jaccard similarity on
        query tokens. Guarded by: minimum token count, relative-temporal
        exclusion, and configurable threshold.

    Usage::

        cache = RecallCache(max_size=256, ttl_seconds=300, fuzzy_threshold=0.7)

        key = RecallCacheKey.build(...)

        # Tier 0
        cached = cache.get(key)
        if cached is not None:
            return cached

        # Tier 1 (automatic Tier 0 miss fallback)
        cached = cache.find_similar(key)
        if cached is not None:
            return cached

        # Full pipeline ...
        cache.put(key, result)
    """

    def __init__(
        self,
        max_size: int = 256,
        ttl_seconds: int = 300,
        fuzzy_threshold: float = 0.7,
        fuzzy_min_tokens: int = 2,
    ):
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._fuzzy_threshold = fuzzy_threshold
        self._fuzzy_min_tokens = fuzzy_min_tokens
        self._cache: OrderedDict[RecallCacheKey, _CacheEntry] = OrderedDict()
        self._bank_generations: dict[str, int] = {}
        self._lock = threading.Lock()
        # Stats
        self._hits = 0
        self._fuzzy_hits = 0
        self._misses = 0

    # --- Tier 0: exact match ---

    def get(self, key: RecallCacheKey) -> Any | None:
        """Tier 0: exact key lookup. Returns None on miss, expiry, or stale bank."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None

            if not self._is_valid(key, entry):
                del self._cache[key]
                self._misses += 1
                return None

            self._cache.move_to_end(key)
            self._hits += 1
            return entry.result

    # --- Tier 1: fuzzy match ---

    def find_similar(self, key: RecallCacheKey) -> Any | None:
        """Tier 1: fuzzy Jaccard match on query tokens.

        Only called after Tier 0 misses. Returns the highest-similarity
        match above threshold, or None.

        Safety guards:
        - Relative temporal expressions in query → skip (results are time-dependent)
        - Fewer than ``fuzzy_min_tokens`` meaningful tokens → skip
        - All non-query parameters must match exactly
        - Cached entry's max_tokens must be ≥ requested max_tokens
        """
        if self._fuzzy_threshold <= 0:
            return None

        # Guard: relative temporal expressions
        if _has_relative_temporal(key.query_normalized):
            return None

        query_tokens = _tokenize_query(key.query_normalized)

        # Guard: too few meaningful tokens → high false-positive risk
        if len(query_tokens) < self._fuzzy_min_tokens:
            return None

        with self._lock:
            best_result = None
            best_sim = self._fuzzy_threshold

            for cached_key, entry in self._cache.items():
                # Exact match on all non-query parameters
                if not key._params_match(cached_key):
                    continue

                # TTL + generation check
                if not self._is_valid(cached_key, entry):
                    continue

                # Jaccard on pre-computed tokens
                sim = _jaccard(query_tokens, entry.query_tokens)
                if sim > best_sim:
                    best_sim = sim
                    best_result = entry.result

            if best_result is not None:
                self._fuzzy_hits += 1
                return best_result

        return None

    # --- Store ---

    def put(self, key: RecallCacheKey, result: Any) -> None:
        """Store a result in the cache with pre-computed query tokens."""
        query_tokens = _tokenize_query(key.query_normalized)

        with self._lock:
            current_gen = self._bank_generations.get(key.bank_id, 0)

            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = _CacheEntry(
                    result=result,
                    created_at=time.time(),
                    bank_generation=current_gen,
                    query_tokens=query_tokens,
                )
                return

            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)

            self._cache[key] = _CacheEntry(
                result=result,
                created_at=time.time(),
                bank_generation=current_gen,
                query_tokens=query_tokens,
            )

    # --- Invalidation ---

    def invalidate_bank(self, bank_id: str) -> None:
        """Bump the generation counter for *bank_id*, invalidating all its entries.

        Entries are lazily evicted on next ``get()`` / ``find_similar()``
        rather than eagerly scanned, so this is O(1).
        """
        with self._lock:
            self._bank_generations[bank_id] = self._bank_generations.get(bank_id, 0) + 1

    def clear(self) -> None:
        """Drop all entries and reset stats."""
        with self._lock:
            self._cache.clear()
            self._bank_generations.clear()
            self._hits = 0
            self._fuzzy_hits = 0
            self._misses = 0

    def stats(self) -> dict[str, Any]:
        """Return cache statistics with separate exact/fuzzy hit counters."""
        with self._lock:
            total = self._hits + self._fuzzy_hits + self._misses
            return {
                "exact_hits": self._hits,
                "fuzzy_hits": self._fuzzy_hits,
                "misses": self._misses,
                "hit_rate": round((self._hits + self._fuzzy_hits) / total, 3) if total > 0 else 0.0,
                "size": len(self._cache),
                "max_size": self._max_size,
                "ttl_seconds": self._ttl_seconds,
                "fuzzy_threshold": self._fuzzy_threshold,
            }

    # --- Internal ---

    def _is_valid(self, key: RecallCacheKey, entry: _CacheEntry) -> bool:
        """Check TTL and bank generation."""
        if time.time() - entry.created_at > self._ttl_seconds:
            return False
        current_gen = self._bank_generations.get(key.bank_id, 0)
        return entry.bank_generation == current_gen
