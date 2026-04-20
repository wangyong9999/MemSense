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

An optional Redis secondary layer can be plugged in so Tier 0 hits are
shared across replicas. Redis is exact-match only; Tier 1 fuzzy stays
local because scanning the whole keyspace per recall is prohibitive.

This module is intentionally self-contained — it depends only on Python
stdlib (plus an optional Redis client imported lazily) and has no imports
from memory_engine or other engine internals, keeping the merge surface
with upstream Hindsight minimal.

Design informed by tiered retrieval strategies in agent memory systems.
"""

from __future__ import annotations

import hashlib
import logging
import pickle
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
    cluster_generation: int | None = None  # Redis gen at put time (None when no secondary)


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

    # How long to trust a cached cluster generation before re-fetching from
    # Redis. Short enough to keep cross-replica invalidation windows tight,
    # long enough to avoid a Redis GET on every local hit under hot load.
    _CLUSTER_GEN_TTL_SECONDS = 2.0

    def __init__(
        self,
        max_size: int = 256,
        ttl_seconds: int = 300,
        fuzzy_threshold: float = 0.7,
        fuzzy_min_tokens: int = 2,
        secondary: "RedisSecondaryCache | None" = None,
    ):
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._fuzzy_threshold = fuzzy_threshold
        self._fuzzy_min_tokens = fuzzy_min_tokens
        self._cache: OrderedDict[RecallCacheKey, _CacheEntry] = OrderedDict()
        self._bank_generations: dict[str, int] = {}
        # bank_id -> (cluster_gen, fetched_at) — tiny TTL cache of the Redis
        # generation counter so we don't pay a Redis RTT on every local hit.
        self._cluster_gen_cache: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()
        self._secondary = secondary
        # Stats
        self._hits = 0
        self._fuzzy_hits = 0
        self._secondary_hits = 0
        self._misses = 0
        self._cluster_gen_evictions = 0

    # --- Tier 0: exact match ---

    def get(self, key: RecallCacheKey) -> Any | None:
        """Tier 0: exact key lookup. Returns None on miss, expiry, or stale bank.

        On local miss falls back to the Redis secondary (if configured) and
        repopulates the local cache on secondary hit so subsequent fuzzy
        lookups (Tier 1) can use it.
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is not None:
                if not self._is_valid(key, entry):
                    del self._cache[key]
                else:
                    self._cache.move_to_end(key)
                    self._hits += 1
                    return entry.result

        if self._secondary is not None:
            result = self._secondary.get(key)
            if result is not None:
                # Repopulate local cache so Tier 1 can reuse the query tokens.
                self.put(key, result, replicate_to_secondary=False)
                with self._lock:
                    self._secondary_hits += 1
                return result

        with self._lock:
            self._misses += 1
        return None

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

    def put(self, key: RecallCacheKey, result: Any, *, replicate_to_secondary: bool = True) -> None:
        """Store a result in the cache with pre-computed query tokens.

        When ``replicate_to_secondary`` is true (default), also write through
        to the Redis secondary so other replicas can Tier-0 hit.
        """
        query_tokens = _tokenize_query(key.query_normalized)
        cluster_gen = self._get_cluster_gen(key.bank_id)

        with self._lock:
            current_gen = self._bank_generations.get(key.bank_id, 0)

            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = _CacheEntry(
                    result=result,
                    created_at=time.time(),
                    bank_generation=current_gen,
                    query_tokens=query_tokens,
                    cluster_generation=cluster_gen,
                )
            else:
                while len(self._cache) >= self._max_size:
                    self._cache.popitem(last=False)
                self._cache[key] = _CacheEntry(
                    result=result,
                    created_at=time.time(),
                    bank_generation=current_gen,
                    query_tokens=query_tokens,
                    cluster_generation=cluster_gen,
                )

        if replicate_to_secondary and self._secondary is not None:
            self._secondary.put(key, result)

    # --- Invalidation ---

    def invalidate_bank(self, bank_id: str) -> None:
        """Bump the generation counter for *bank_id*, invalidating all its entries.

        Entries are lazily evicted on next ``get()`` / ``find_similar()``
        rather than eagerly scanned, so this is O(1). The Redis secondary
        (if any) is invalidated by the same mechanism (incr on its own
        generation counter).
        """
        with self._lock:
            self._bank_generations[bank_id] = self._bank_generations.get(bank_id, 0) + 1
            # Drop any cached cluster_gen for this bank so the next read
            # re-fetches from Redis (keeps cross-replica windows tight after
            # any invalidation on this replica).
            self._cluster_gen_cache.pop(bank_id, None)
        if self._secondary is not None:
            self._secondary.invalidate_bank(bank_id)

    def clear(self) -> None:
        """Drop all entries and reset stats."""
        with self._lock:
            self._cache.clear()
            self._bank_generations.clear()
            self._cluster_gen_cache.clear()
            self._hits = 0
            self._fuzzy_hits = 0
            self._secondary_hits = 0
            self._misses = 0
            self._cluster_gen_evictions = 0
        if self._secondary is not None:
            self._secondary.clear()

    def stats(self) -> dict[str, Any]:
        """Return cache statistics with separate exact/fuzzy/secondary hit counters."""
        with self._lock:
            total = self._hits + self._fuzzy_hits + self._secondary_hits + self._misses
            base = {
                "exact_hits": self._hits,
                "fuzzy_hits": self._fuzzy_hits,
                "secondary_hits": self._secondary_hits,
                "cluster_gen_evictions": self._cluster_gen_evictions,
                "misses": self._misses,
                "hit_rate": round(
                    (self._hits + self._fuzzy_hits + self._secondary_hits) / total,
                    3,
                )
                if total > 0
                else 0.0,
                "size": len(self._cache),
                "max_size": self._max_size,
                "ttl_seconds": self._ttl_seconds,
                "fuzzy_threshold": self._fuzzy_threshold,
            }
        if self._secondary is not None:
            base.update(self._secondary.stats())
        return base

    # --- Internal ---

    def _is_valid(self, key: RecallCacheKey, entry: _CacheEntry) -> bool:
        """Check TTL and bank generation (local + cluster-wide)."""
        if time.time() - entry.created_at > self._ttl_seconds:
            return False
        current_gen = self._bank_generations.get(key.bank_id, 0)
        if entry.bank_generation != current_gen:
            return False
        # Cluster generation: if we wrote an entry while the secondary was
        # active, check it still matches — otherwise a peer replica's
        # invalidation is silently ignored here.
        if entry.cluster_generation is not None and self._secondary is not None:
            cluster_gen = self._get_cluster_gen(key.bank_id)
            if cluster_gen is not None and entry.cluster_generation != cluster_gen:
                self._cluster_gen_evictions += 1
                return False
        return True

    def _get_cluster_gen(self, bank_id: str) -> int | None:
        """Return the cluster-wide Redis generation for ``bank_id``, cached
        for ``_CLUSTER_GEN_TTL_SECONDS`` so recall hot loops don't pay a
        Redis RTT on every hit. Returns ``None`` if the secondary is not
        configured or transiently fails.
        """
        if self._secondary is None:
            return None
        cached = self._cluster_gen_cache.get(bank_id)
        now = time.time()
        if cached is not None and now - cached[1] < self._CLUSTER_GEN_TTL_SECONDS:
            return cached[0]
        try:
            gen = self._secondary._current_gen(bank_id)
        except Exception:
            return cached[0] if cached is not None else None
        self._cluster_gen_cache[bank_id] = (gen, now)
        return gen


# ---------------------------------------------------------------------------
# Redis secondary cache (shared across replicas, exact-match only)
# ---------------------------------------------------------------------------


def _hash_key(key: RecallCacheKey) -> str:
    """Stable SHA256 of the key tuple, truncated to 24 hex chars."""
    raw = repr(
        (
            key.bank_id,
            key.query_normalized,
            tuple(sorted(key.fact_types)),
            key.budget_value,
            key.max_tokens,
            tuple(sorted(key.tags)),
            key.tags_match,
            key.question_date,
            key.include_entities,
            key.include_chunks,
            key.include_source_facts,
        )
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


_SIGNATURE_ALGO = "sha256"
_ENVELOPE_VERSION = b"v1"


def _sign(secret: bytes, payload: bytes) -> bytes:
    import hmac

    return hmac.new(secret, payload, _SIGNATURE_ALGO).digest()


def _seal(secret: bytes, payload: bytes) -> bytes:
    """Wrap ``payload`` in a versioned + HMAC-authenticated envelope.

    Envelope format (binary):
        b"v1" || mac(32 bytes) || payload

    The version prefix lets us roll forward to a different algorithm
    without false-positives against legacy unsigned blobs.
    """
    return _ENVELOPE_VERSION + _sign(secret, payload) + payload


def _unseal(secret: bytes, sealed: bytes) -> bytes | None:
    """Verify and strip the envelope. Returns the inner payload on success,
    ``None`` on any tampering / format error / missing signature.
    """
    import hmac

    if not sealed.startswith(_ENVELOPE_VERSION):
        return None
    body = sealed[len(_ENVELOPE_VERSION) :]
    if len(body) < 32:
        return None
    mac = body[:32]
    payload = body[32:]
    expected = _sign(secret, payload)
    if not hmac.compare_digest(mac, expected):
        return None
    return payload


class RedisSecondaryCache:
    """Exact-match Tier 0 cache backed by Redis, for cross-replica sharing.

    Entries are stored as HMAC-authenticated envelopes: an attacker who can
    inject or modify payloads in Redis cannot cause arbitrary code execution
    on read, because ``get()`` verifies the MAC BEFORE ``pickle.loads``. A
    tampered or unsigned blob is rejected as a cache miss.

    Envelope format: ``b"v1" || hmac_sha256(secret, payload)(32) || payload``.
    The payload is a pickle of ``{"gen": <int>, "result": <RecallResult>}``.

    Per-bank invalidation bumps a generation counter at
    ``recall_cache_gen:<bank_id>`` so in-flight entries become stale without
    needing a keyspace scan.

    All Redis-side operations fail gracefully: any exception is logged and
    treated as a cache miss, so a flaky Redis never blocks the recall pipeline.
    """

    def __init__(
        self,
        url: str,
        signing_key: bytes,
        ttl_seconds: int = 300,
        prefix: str = "recall_cache",
    ):
        try:
            import redis
        except ImportError as exc:
            raise RuntimeError(
                "Redis recall cache requires the 'redis' package. "
                "Install with: pip install 'memsense-api-slim[cache-redis]'"
            ) from exc

        if not signing_key or len(signing_key) < 16:
            raise RuntimeError(
                "Redis recall cache requires a signing key of at least 16 bytes. "
                "Set HINDSIGHT_API_RECALL_CACHE_SIGNING_KEY to a high-entropy "
                "secret (same value across all replicas)."
            )

        self._client = redis.Redis.from_url(url, socket_timeout=1.0, socket_connect_timeout=1.0)
        self._signing_key = signing_key
        self._ttl_seconds = ttl_seconds
        self._prefix = prefix
        self._hits = 0
        self._misses = 0
        self._errors = 0
        self._rejected = 0
        self._lock = threading.Lock()

    def _entry_key(self, key: RecallCacheKey) -> str:
        return f"{self._prefix}:{key.bank_id}:{_hash_key(key)}"

    def _gen_key(self, bank_id: str) -> str:
        return f"{self._prefix}_gen:{bank_id}"

    def _current_gen(self, bank_id: str) -> int:
        try:
            raw = self._client.get(self._gen_key(bank_id))
        except Exception:
            return 0
        return int(raw) if raw is not None else 0

    def get(self, key: RecallCacheKey) -> Any | None:
        try:
            raw = self._client.get(self._entry_key(key))
        except Exception:
            with self._lock:
                self._errors += 1
            logger.debug("recall_cache redis get failed", exc_info=True)
            return None

        if raw is None:
            with self._lock:
                self._misses += 1
            return None

        # Verify the envelope BEFORE deserializing. A tampered or unsigned
        # blob is rejected outright — pickle.loads never sees it, so
        # attacker-supplied __reduce__ payloads cannot execute.
        payload = _unseal(self._signing_key, raw)
        if payload is None:
            with self._lock:
                self._rejected += 1
                self._misses += 1
            logger.warning("recall_cache redis rejected unsigned/tampered payload")
            return None

        try:
            parsed = pickle.loads(payload)
            stored_gen = parsed["gen"]
            current_gen = self._current_gen(key.bank_id)
            if stored_gen != current_gen:
                with self._lock:
                    self._misses += 1
                return None
            with self._lock:
                self._hits += 1
            return parsed["result"]
        except Exception:
            with self._lock:
                self._errors += 1
            logger.debug("recall_cache redis decode failed", exc_info=True)
            return None

    def put(self, key: RecallCacheKey, result: Any) -> None:
        try:
            gen = self._current_gen(key.bank_id)
            payload = pickle.dumps({"gen": gen, "result": result}, protocol=pickle.HIGHEST_PROTOCOL)
            sealed = _seal(self._signing_key, payload)
            self._client.setex(self._entry_key(key), self._ttl_seconds, sealed)
        except Exception:
            with self._lock:
                self._errors += 1
            logger.debug("recall_cache redis put failed", exc_info=True)

    def invalidate_bank(self, bank_id: str) -> None:
        try:
            self._client.incr(self._gen_key(bank_id))
        except Exception:
            with self._lock:
                self._errors += 1
            logger.debug("recall_cache redis invalidate failed", exc_info=True)

    def clear(self) -> None:
        # Expensive operation; used only by tests / admin. Best-effort.
        try:
            cursor = 0
            pattern = f"{self._prefix}*"
            while True:
                cursor, keys = self._client.scan(cursor=cursor, match=pattern, count=500)
                if keys:
                    self._client.delete(*keys)
                if cursor == 0:
                    break
        except Exception:
            with self._lock:
                self._errors += 1
            logger.debug("recall_cache redis clear failed", exc_info=True)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            return {
                "redis_hits": self._hits,
                "redis_misses": self._misses,
                "redis_errors": self._errors,
                "redis_rejected": self._rejected,
                "redis_hit_rate": round(self._hits / total, 3) if total > 0 else 0.0,
            }
