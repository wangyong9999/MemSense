# Upstream merge-safety audit — v0.6 additions

Run against `upstream/main` at the time of this audit (commit `2b12a794`
Merge upstream/main on our side). All v0.6 additions preserve mechanical
merge behavior. Re-run this audit after each `sync-upstream.sh` to catch
drift early.

## Method

```bash
git diff upstream/main...HEAD -- hindsight-api-slim/hindsight_api/ \
  | grep -E "^diff --git" | sort
```

Then for each upstream-tracked file, check the diff is **additions only**
(no semantic removals beyond reformatting).

## Upstream-tracked files touched by v0.6

| File | Insertions | Deletions | Shape |
|---|---:|---:|---|
| `api/http.py` | 65 | 0 | `/token-usage` endpoint (from earlier token accounting work) + 4-line `register_memsense_routes(app)` hook block |
| `engine/memory_engine.py` | 91 | 1 | `_invalidate_recall_cache` helper + 3 hook sites (retain/consolidate/delete) + recall cache init block with Redis secondary |
| `engine/retain/orchestrator.py` | 29 | 0 | single enrichment call block (branches into date/detail/format/pii) |
| `config.py` | 65 | 3 | contiguous MemSense env-var block + field block + `from_env` init lines |
| `pyproject.toml` | 8 | 0 | new `cache-redis` optional extra + `fakeredis` test dep |

Every insertion sits in a contiguous block wrapped by `# MemSense ...`
comments. None of them overlap upstream's typical edit zones (LLM
providers, storage modules, test fixtures) observed over the last 40+
upstream commits.

## Fork-only new files (zero merge surface)

```
hindsight_api/api/erasure.py
hindsight_api/api/memsense_routes.py
hindsight_api/api/usage.py
hindsight_api/engine/retain/post_extraction/pii_redact.py
hindsight_api/engine/search/recall_cache.py                 (MemSense from day 1)
hindsight_api/engine/token_accounting.py                    (MemSense from day 1)
hindsight_api/alembic/versions/l8g9h0i1j2k3_create_token_usage_table.py
scripts/benchmarks/run-comparison.sh
scripts/benchmarks/_comparison_summary.py
hindsight-dev/benchmarks/comparison/README.md
tests/test_erasure_endpoint.py
tests/test_usage_endpoint.py
(plus additions to existing tests/test_recall_cache.py and tests/test_post_extraction.py — additive only)
```

## Risk registers per file

**`config.py`** — the one file that will regularly pick up upstream
additions (new LLM providers, reranker backends, etc.). MemSense
additions live in a dedicated contiguous section at lines ~375-400
(`# MemSense ...` env vars) and lines ~1050-1065 (dataclass fields).
Conflict probability on each sync: medium, resolvable by placing
upstream's new fields above our section. **Mitigation**: `sync-upstream.sh`
runs the fork's own test suite after merge so conflicts surface as red
builds rather than silent breakage.

**`memory_engine.py`** — the recall-cache init block is near
`__init__` where upstream frequently adds new config defaults. Single
hook points for cache invalidation are at stable call sites (end of
retain / end of consolidate / end of delete_bank). **Mitigation**: the
`_invalidate_recall_cache` helper keeps hook lines to one line each,
minimising rebase surface.

**`orchestrator.py`** — single enrichment block near the end of
`_extract_and_embed`. Upstream has not touched this region in the last
year of commits per `git log`. **Mitigation**: the block is
self-contained — if upstream refactors around it, the block moves with
the function.

**`http.py`** — single hook `register_memsense_routes(app)` right
after `_register_routes(app)`. Very stable anchor. **Mitigation**:
hook is a 3-line block; easy to relocate.

**`pyproject.toml`** — additions to `[project.optional-dependencies]`
and `[test]` groups. Upstream touches these on dep bumps. **Mitigation**:
section is append-only on our side; merge tooling handles.

## Verdict

Merge surface is minimal and additive. Upstream sync remains
mechanical; any future conflicts are confined to predictable sections
and surfaced by the post-merge test run in `scripts/sync-upstream.sh`.
