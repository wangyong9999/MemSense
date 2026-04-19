# v0.6 roadmap — enterprise commercial readiness

Scope: four feature tracks that turn MemSense from "OSS fork with flags" into "enterprise-pilot-ready memory system with measured advantage." All additions MemSense-only, flag-gated, off by default — so upstream merges stay mechanical and customers opt in per feature.

Priorities are ranked by commercial ROI, not engineering size.

---

## P2 — Compliance minimum (legal unblock)

Goal: pass legal review at enterprise POC.

### P2a — PII redactor
- File: `hindsight-api-slim/hindsight_api/engine/retain/post_extraction/pii_redact.py` (new, fork-only)
- Patterns: email, phone (intl + US), SSN, credit card (Luhn-checked), IPv4
- Hook: slot into `post_extraction/enrichment.py` as a new step after `fact_format_clean`
- Flag: `HINDSIGHT_API_RETAIN_PII_REDACT_ENABLED` (off by default)
- Output: matched text replaced with `[REDACTED:<type>]`
- Tests: unit tests per pattern, integration test proving redacted fact is persisted

### P2b — GDPR erase endpoint
- File: `hindsight-api-slim/hindsight_api/api/erasure.py` (new, fork-only)
- Endpoint: `POST /v1/{tenant}/banks/{bank_id}/erase`
- Behavior: hard-delete all memory_units, entity_links, documents, embeddings for a bank; the bank row itself survives (reset) unless `?drop_bank=true` is passed
- Flag: `HINDSIGHT_API_ERASURE_API_ENABLED` (off by default)
- Mounts via a single hook in http.py (one-liner, behind flag)
- Tests: integration test against test DB verifying all rows gone + audit event emitted

## P3 — Usage reporting (pricing model prerequisite)

- File: `hindsight-api-slim/hindsight_api/api/usage.py` (new, fork-only)
- Endpoint: `GET /v1/{tenant}/usage?bank_id=&start=&end=&group_by={operation|bank|day}`
- Aggregates existing `token_usage` table (already fork-only, created in migration `l8g9h0i1j2k3`)
- Returns: input/output/context token totals, saved_tokens, operation counts, per-group breakdown
- Flag: `HINDSIGHT_API_USAGE_API_ENABLED` (off by default)
- Tests: integration with seeded token_usage rows

## P1 — Recall cache production-ready

Current state: in-process LRU in `engine/search/recall_cache.py`. Doesn't survive restart, doesn't share across replicas.

- Extend cache with a backend protocol; add `RedisRecallCacheBackend`
- Env: `HINDSIGHT_API_RECALL_CACHE_BACKEND` = `memory|redis` (default `memory`)
- Env: `HINDSIGHT_API_RECALL_CACHE_REDIS_URL` = `redis://host:port/db`
- If Redis URL set but unreachable, log warning and fall back to memory backend (dev ergonomics)
- Prometheus counters: `hindsight_recall_cache_hits_total{tier=}`, `..._misses_total`, `..._evictions_total`
- Tests: unit test the Redis backend against `fakeredis`
- Still off by default — enable after P0 benchmarks prove net-positive

## P0 — Benchmark comparison harness

Current state: LongMemEval + LoCoMo runners exist, some individual runs produced, no public comparison published.

- Script: `scripts/benchmarks/run-comparison.sh`
- Runs the 4-cell matrix:
  1. Baseline (upstream defaults, all MemSense flags off)
  2. +Enrichment (`RETAIN_POST_EXTRACTION_ENABLED=true`, `RETAIN_FACT_FORMAT_CLEAN_ENABLED=true`)
  3. +Recall cache (`RECALL_CACHE_ENABLED=true`)
  4. All flags on
- Writes JSON to `hindsight-dev/benchmarks/comparison/results-<timestamp>.json`
- Template: `hindsight-dev/benchmarks/comparison/README.md` — table scaffold for accuracy delta, p50/p99 latency, cache hit rate
- User runs when LLM keys + time budget available; harness is one command

---

## Out of scope (v0.7+)

- Full AuthN/AuthZ (OIDC, SAML, bank-level RBAC) — needs product decision on build vs buy (Auth0, WorkOS, Clerk)
- Audit log table with fork-owned migration — existing `audit_logger` on `app.state` is enough for v0.6; dedicated table is v0.7
- K8s operator
- Semantic cache (embed-based query similarity) — wait for distributed recall cache telemetry first

## Commit cadence

One commit per track; each commit self-contained (code + tests + config entry + docs). Lint runs after each (`./scripts/hooks/lint.sh`). No commit touches an upstream file beyond a one-liner hook.

## Reference

- `hindsight-dev/planning/RELEASE_ALIGNMENT.md` — release infrastructure checklist
- `docs/PACKAGES.md` — package layout explanation
- `CLAUDE.md` — fork convention (7 rules)
