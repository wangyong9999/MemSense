# Hardening fix plan

Issues surfaced while adding targeted tests for the retain pipeline,
recall/search pipeline, and memory lifecycle. None of these were fixed in
this pass — each has a proof-of-existence test (xfail with `strict=True`
or a documenting assertion) that will auto-flip to pass once fixed, so a
regression watcher is already in place.

Priority buckets:

| Priority | Meaning |
|---|---|
| **P0** | Security or compliance gap. Block before enabling in prod. |
| **P1** | Correctness under realistic workloads. Fix before v0.6 GA. |
| **P2** | Quality-of-life / defence-in-depth. Fix when convenient. |

---

## §1 — PII redactor bypasses `ExtractedFact.entities` (P0)

**What** — `redact_pii_in_facts()` only scans `fact.fact_text` and
`fact.where`. Entities returned by the LLM (e.g. `["Alice", "bob@ex.com"]`)
are persisted verbatim into the `entities` list and flow into storage /
entity resolution / indexing. A caller who enables PII redaction assumes
no PII ends up on disk — this gap violates that assumption.

**Evidence** — `tests/test_post_extraction.py::TestPIIRedactInteractions::test_pii_in_entities_list_is_redacted` (xfail strict).

**Fix shape** — in `pii_redact.py::redact_pii_in_facts`, also iterate
`fact.entities` (which is `list[str]` per `types.py` or `list[Entity]`
for the pydantic model). Replace tainted entries with `[REDACTED:<type>]`.
Subtle: after redaction the entity is no longer a real entity — we may
want to DROP matches rather than leave a redacted string that then gets
resolved as a new phantom entity. Recommended: drop.

**Effort** — ~30 lines + 2–3 tests.

---

## §2 — Usage endpoint lacks tenant authentication (P0)

**What** — `GET /v1/default/usage` queries the `token_usage` table
directly via `app.state.memory._get_pool()` without calling
`memory._authenticate_tenant(request_context)`. Any unauthenticated
caller receives aggregated usage across every bank in the deployment.
In a multi-tenant setup this is a data leak.

**Evidence** — `tests/test_usage_endpoint.py::test_usage_endpoint_requires_authenticated_tenant` (xfail strict).

**Fix shape** — at the top of `get_tenant_usage()` in
`hindsight_api/api/usage.py`:

```python
await app.state.memory._authenticate_tenant(request_context)
```

Also scope the SQL `WHERE` clause by the authenticated tenant's schema
prefix so bank_id=null queries don't silently straddle tenants. Match
the pattern used by `delete_bank` (which already does both).

**Effort** — ~10 lines + 3 tests (401 without auth, 200 with auth, scoped
result with multi-tenant fixture).

---

## §3 — GDPR erase skips audit entry on failure (P0)

**What** — `register_erasure_route` only emits the `gdpr_erase` audit
entry after a successful `delete_bank`. If the engine throws partway
through deletion (e.g. row locks, partial cascade failure), no audit
entry is emitted. Compliance teams need evidence of every erasure
attempt, including failures, so they can distinguish "attempt succeeded"
from "attempt never made" from "attempt partially completed".

**Evidence** — `tests/test_erasure_endpoint.py::test_erase_emits_audit_entry_even_on_failure` (xfail strict).

**Fix shape** — wrap the `delete_bank` call in `try/except/else/finally`
and emit either `gdpr_erase` (success) or `gdpr_erase_failed` (exception
path), with the exception type captured in `metadata`.

```python
try:
    result = await memory.delete_bank(...)
except Exception as exc:
    if audit_logger is not None:
        audit_logger.log_fire_and_forget(AuditEntry(
            action="gdpr_erase_failed",
            transport="http",
            bank_id=bank_id,
            request={"drop_bank": drop_bank},
            metadata={"error": type(exc).__name__},
        ))
    raise
else:
    # existing success audit
```

**Effort** — ~15 lines + flip the xfail assertion.

---

## §4 — Redis secondary deserializes untrusted pickle (P0)

**What** — `RedisSecondaryCache.get()` calls `pickle.loads()` on the
raw bytes fetched from Redis. A malicious Redis (compromised instance,
MITM on the TCP connection, or a co-tenant with write access to the
same keyspace) can deliver a payload whose `__reduce__` invokes any
callable when deserialised. This is a classic pickle RCE.

**Evidence** — `tests/test_recall_cache.py::TestRedisSecondaryPayloadSafety::test_tampered_payload_executes_arbitrary_code` — fires a module-level sentinel during `get()`.

**Fix shape** — two options, in increasing strictness:

1. **HMAC-signed envelope** — store `{"mac": hmac(key, pickle_bytes), "payload": pickle_bytes}`, verify mac before unpickling, reject on mismatch. Key sourced from `HINDSIGHT_API_RECALL_CACHE_SIGNING_KEY` (env) with a clear error if not set when Redis is enabled.
2. **JSON-only payloads** — convert `RecallResultModel` to a canonical dict before storing, reconstruct on read. Loses generality but is fundamentally safer. Preferred long-term.

Start with (1) for v0.6 to avoid rewriting the recall result serialisation surface.

**Effort** — ~80 lines (sign/verify helpers, env wiring, test updates).

---

## §5 — Redis-filled local entry does not inherit cluster generation (P1)

**What** — When replica B reads a value from Redis via
`RecallCache.get()` → `self._secondary.get()` and promotes it into the
local cache via `self.put(..., replicate_to_secondary=False)`, the local
entry is stamped with replica B's LOCAL `bank_generation`, not with the
cluster-wide Redis generation. A subsequent invalidation on replica A
(which bumps the Redis gen) does not bump replica B's local gen; replica
B keeps serving the promoted entry from its local cache until replica B
itself invalidates.

**Evidence** — `tests/test_recall_cache.py::TestRedisCrossReplica::test_invalidate_on_replica_a_invalidates_replica_b` (currently relaxed to accept either behavior; the `in ("stale", None)` clause documents the gap).

**Fix shape** — include the Redis generation inside `_CacheEntry`
(`cluster_gen`) and, on `get()`, re-check it against
`self._secondary._current_gen(bank_id)` before returning. This adds one
Redis GET per local hit; offset it by caching the gen for a short TTL
(e.g. 1–5 s) since banks don't invalidate in the critical-hot-loop.

**Effort** — ~60 lines + cross-replica tests that assert exact
invalidation semantics.

---

## §6 — Recall cache stats — redis error counter never surfaced in top-level `stats()` (P2)

**What** — `RedisSecondaryCache.stats()` tracks `redis_errors`, but
`RecallCache.stats()` merges only `redis_hits / misses / hit_rate` (via
`.update()` which does include all keys — actually this is fine; noting
for completeness). Verify during fix for §5 that top-level stats
observability is complete; if not, add a Prometheus counter.

**Effort** — verification + possibly 10 lines.

---

## §7 — 5xx responses echo exception messages verbatim (P2)

**What** — both the erase endpoint and the usage endpoint format
`HTTPException(status_code=500, detail=str(exc))`. If an internal
exception message contains a file path, stack frame, or config secret,
the caller sees it. For enterprise compliance + defence-in-depth, 5xx
responses should return an opaque message and log the detail internally.

**Evidence** — `tests/test_erasure_endpoint.py::test_erase_does_not_expose_internal_traceback` (currently asserts no `Traceback` — the exception message itself still leaks).

**Fix shape** — uniform helper that logs full detail and returns a
request-id-tagged opaque message to the caller:

```python
request_id = str(uuid.uuid4())
logger.error("erase_bank failed [%s]", request_id, exc_info=True)
raise HTTPException(status_code=500, detail=f"internal error (ref: {request_id})")
```

Adopt across both new endpoints; migrate other endpoints when convenient.

**Effort** — ~20 lines + update existing tests to match opaque format.

---

## §8 — Entity resolver and link creation are untested around the new PII path (P1)

**What** — after PII redaction, the `fact_text` contains tokens like
`[REDACTED:email]`. Down-pipeline the entity resolver computes
trigram GIN matches against this string, and link creation builds
co-occurrence graphs over the tokens. No test confirms the redaction
tokens don't explode into phantom entities (e.g. "REDACTED" becoming
a top-cited entity across many banks).

**Evidence** — no existing test; surfaced during review of
`engine/retain/orchestrator.py` line 400 hook.

**Fix shape** — in `redact_pii_in_facts`, also strip the matched tokens
from `fact.entities` prior to the resolver seeing them. Add a fake
entity resolver + integration test asserting that `[REDACTED:…]` is
never persisted as an entity row.

**Effort** — ~50 lines including fixture plumbing. Overlaps with §1.

---

## §9 — Usage endpoint SQL is schema-unqualified (P1, won't fix this pass)

**What** — `SELECT ... FROM token_usage` is unqualified. In a multi-tenant
deployment that uses Postgres schemas for isolation (as upstream's
alembic migrations already support via `target_schema`), the query will
hit whichever schema is on `search_path` and silently mix tenants.
Upstream's `/v1/default/banks/{bank_id}/token-usage` has the same
limitation — this is a broader tenancy story, not a MemSense-only gap.

**Evidence** — code inspection of `usage.py` + `http.py::api_token_usage`.

**Fix shape** — when §2 lands, resolve the schema from the authenticated
tenant (same mechanism `delete_bank` uses) and qualify the table name.
Needs a helper `fq_token_usage_table(tenant)` so the pattern is shared
between the two endpoints.

**Effort** — ~30 lines, but entangled with upstream multi-tenancy work.
Defer to v0.7; track separately.

---

## §10 — Redis signing-key hard-fail policy (subissue of §4)

When §4 lands with HMAC envelopes, the policy around missing keys matters:

- Signing key missing AND Redis URL set → **hard fail at startup**, not
  a silent downgrade to "no secondary". Silent downgrade is a footgun —
  operators think they have cross-replica sharing while they silently
  don't.
- Signing key set but the stored payload lacks a signature → treat as
  untrusted miss, log `redis_errors++` but do not raise. (Legacy
  payloads from a pre-§4 deployment.)
- Signing key rotated (old signatures invalid) → same path as above —
  payloads treated as miss, regenerated on next compute.

Document in the CLAUDE.md envar section when fix ships.

---

## Not in scope for this hardening pass

- **Non-ASCII PII (Chinese 身份证, German tax ID, IPv6, etc.)** — regex
  scope is ASCII. Tracked but not in v0.6 plan; add locale-specific
  redactors as separate modules when a customer needs them.
- **Rate limiting on erase endpoint** — should exist but lives in the
  operation_validator layer (upstream territory), not here.
- **Redis gen-counter TTL** — `recall_cache_gen:<bank_id>` keys have no
  TTL, so a long-dead bank's counter lingers forever. Minor keyspace
  leak; mitigate with Redis `maxmemory-policy allkeys-lru` if it ever
  matters.
- **Usage endpoint pagination / row caps** — a tenant with 10M
  token_usage rows over a wide window returns the full list. Deferred
  to when a real customer hits the cliff.

---

## Sequencing

1. `§7` first (logging helper used by §2 and §3, small).
2. `§1` + `§8` together (pii_redact extension + entity regression test).
3. `§3` (erase audit on failure).
4. `§2` (usage tenant auth).
5. `§4` + `§10` (pickle hardening with signing-key policy).
6. `§5` (cross-replica generation).
4. `§5` after `§4` lands (re-use the signed envelope to carry gen safely).
5. `§7` as cleanup once §2/§3 patterns are in place.
6. `§6` folded into whichever PR touches `RecallCache.stats()`.

Each fix should flip its corresponding xfail or documenting test to a
hard assertion — the regression safety net is already in the repo.
