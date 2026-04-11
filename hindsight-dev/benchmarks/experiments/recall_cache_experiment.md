# Experiment: Recall Result Cache (OPTIMIZATION_INSIGHTS 2.2)

Date: 2026-04-10
Status: **Validated — cache hit latency ~0ms vs ~2.8s baseline**

## Hypothesis

Caching recall results for identical queries to the same bank can skip the full
4-way retrieval + RRF + cross-encoder pipeline (~2.8s), reducing latency to near-zero
for repeated queries and cutting LLM/embedding compute costs.

## Implementation

Feature flag: `HINDSIGHT_API_RECALL_CACHE_ENABLED` (default: false)
Config: `HINDSIGHT_API_RECALL_CACHE_MAX_SIZE` (default: 256), `HINDSIGHT_API_RECALL_CACHE_TTL_SECONDS` (default: 300)

Files created (independent, minimal coupling to upstream Hindsight):
- `engine/search/recall_cache.py` — RecallCache: LRU + TTL + per-bank generation invalidation
- `tests/test_recall_cache.py` — 21 unit tests

Call sites in memory_engine.py (~15 lines total):
- `__init__`: Create cache if enabled (7 lines)
- `recall_async`: Cache check (early return) + cache store after pipeline (9 lines)
- `retain_batch_async`, `delete_memory_unit`, `delete_bank`: Invalidate bank (3 x 2 lines)

### Design Decisions

1. **Cache key excludes `max_tokens`**: Cached results are the full ranked list; token
   filtering is re-applied on hit (microseconds). A `max_tokens=2048` query reuses cache
   from a `max_tokens=4096` call.

2. **Per-bank generation counter for invalidation**: O(1) bump on retain/delete, lazy
   eviction on next `get()`. No eager scan needed.

3. **Thread-safe**: `threading.Lock` protects all mutations (safe for async + thread pool).

4. **In-memory only**: No external dependencies (Redis etc.). Suitable for single-process
   deployments. Multi-process deployments need per-process caches (acceptable — each
   process independently warms up).

## Validation Results

20 questions from conv-48 (bench-locomo-minimax), local embeddings + cross-encoder.

| Scenario | Avg latency/query | vs Baseline |
|----------|-------------------|-------------|
| Cache OFF (baseline) | **2.828s** | — |
| Cache ON (cold pass) | **2.646s** | ~6% overhead of cache key computation |
| Cache ON (warm pass) | **<0.001s** | **~100% reduction** |

Cache stats after test: 20 hits / 20 misses / 50% hit rate (expected for 2-pass test).

### Bank invalidation verified

- 21 unit tests pass covering: hit/miss, TTL expiry, bank invalidation isolation,
  LRU eviction, access-refresh, stats tracking.

## Production Impact Estimate

- **High-frequency query scenarios** (金融: "客户X风险等级", 电网: "设备X状态"):
  First query ~2.8s, subsequent identical queries <1ms within TTL window.
- **Benchmark eval**: No impact (each question is unique, cache miss rate ~100%).
- **Cold start overhead**: Negligible (~0.1ms for cache key computation).
- **Memory**: ~256 entries × ~50KB per RecallResult ≈ ~12MB max. Configurable via max_size.

## Next Steps

- Enable in production: `HINDSIGHT_API_RECALL_CACHE_ENABLED=true`
- Monitor hit rate via `cache.stats()` endpoint (can expose in admin API)
- Consider fuzzy matching (Jaccard on query tokens) for Tier-1 cache in future iteration
