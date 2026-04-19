# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Fork Convention (MemSense on upstream Hindsight)

This repo is a soft fork of `vectorize-io/hindsight`. Upstream is added as the `upstream` remote and merged periodically via `scripts/sync-upstream.sh`. Keep merges mechanical:

1. **Do not rename or move upstream files or directories.** Paths like `hindsight-api-slim`, `hindsight-all`, `hindsight-integrations/<name>`, `helm/`, `docker/`, `hindsight-docs/` stay. Renames turn every merge into tree-conflict resolution.
2. **Fork-only features live in isolated modules we own.** New Python files under `.../engine/<our-feature>/` (e.g. `engine/retain/post_extraction/`, `engine/search/recall_cache.py`). Flags as `HINDSIGHT_API_<FEATURE>_ENABLED` in `config.py`, grouped under `# MemSense ...` comments, default off.
3. **Single flag-gated hook point per feature** inside upstream files. If multiple sites are genuinely needed (e.g. recall cache init + invalidate on retain/delete/consolidation + recall-enter/exit), consolidate repeated logic behind a helper method like `_invalidate_recall_cache(bank_id)` so each site is a one-liner.
4. **Prefer a new file over editing an upstream file.** New endpoint → new `hindsight_api/api/<feature>.py`. New script → our own path. New CI job → new workflow file.
5. **Version numbers track upstream**: our CHANGELOG entry goes ahead of upstream’s latest tag (if upstream is 0.5.3, ours is 0.5.4+). Never reuse an upstream version number.
6. **Sync cadence**: run `scripts/sync-upstream.sh` at least monthly or after an upstream tag. Small merges beat one big merge.
7. **On conflict**, preserve both sides. Fork-only features are additive and never conflict semantically — when `<<<<<<<` appears in an upstream file, resolve by stacking our hook + upstream’s change.

## Project Overview

Hindsight is an agent memory system that provides long-term memory for AI agents using biomimetic data structures. Memories are organized as:
- **World facts**: General knowledge ("The sky is blue")
- **Experience facts**: Personal experiences ("I visited Paris in 2023")
- **Mental models**: Consolidated knowledge synthesized from facts ("User prefers functional programming patterns")

## Development Commands

### Local Development (API + UI)
```bash
# Start both API server and control plane UI
./scripts/dev/start.sh
```

### API Server (Python/FastAPI)
```bash
# Start API server only (loads .env automatically)
./scripts/dev/start-api.sh

# Run all tests (parallelized with pytest-xdist)
cd hindsight-api-slim && uv run pytest tests/

# Run specific test file
cd hindsight-api-slim && uv run pytest tests/test_http_api_integration.py -v

# Run single test function
cd hindsight-api-slim && uv run pytest tests/test_retain.py::test_retain_simple -v

# Lint and format
cd hindsight-api-slim && uv run ruff check .
cd hindsight-api-slim && uv run ruff format .

# Type checking (uses ty - extremely fast type checker from Astral)
cd hindsight-api-slim && uv run ty check hindsight_api/
```

### Control Plane (Next.js)
```bash
./scripts/dev/start-control-plane.sh
# Or manually:
cd hindsight-control-plane && npm run dev
```

### Documentation Site (Docusaurus)
```bash
./scripts/dev/start-docs.sh
```


### Generating Clients/OpenAPI
```bash
# Regenerate OpenAPI spec after API changes (REQUIRED after changing endpoints)
./scripts/generate-openapi.sh

# Regenerate all client SDKs (Python, TypeScript, Rust)
./scripts/generate-clients.sh
```

### Benchmarks
```bash
# Accuracy benchmarks
./scripts/benchmarks/run-longmemeval.sh
./scripts/benchmarks/run-locomo.sh

# Performance benchmarks
./scripts/benchmarks/run-consolidation.sh
./scripts/benchmarks/run-retain-perf.sh --document <path>  # Requires API server running

# Results viewer
./scripts/benchmarks/start-visualizer.sh  # View results at localhost:8001
```

## Architecture

### Monorepo Structure
- **hindsight-api-slim/**: Core FastAPI server with memory engine (Python, uv) — primary API codebase
- **hindsight-api/**: Legacy API package (wraps hindsight-api-slim + hindsight-embed)
- **hindsight-all-slim/**: All-in-one package (API slim + control plane)
- **hindsight-all/**: All-in-one package (API + control plane + embed)
- **hindsight-control-plane/**: Admin UI (Next.js, npm)
- **hindsight-cli/**: CLI tool (Rust, cargo, uses progenitor for API client)
- **hindsight-clients/**: Generated SDK clients (Python, TypeScript, Rust)
- **hindsight-docs/**: Docusaurus documentation site
- **hindsight-embed/**: Embedded local embedding/reranker models
- **hindsight-integrations/**: Framework integrations (LiteLLM, CrewAI, LangGraph, Pydantic AI, AG2, Claude Code, etc.)
- **hindsight-integration-tests/**: Cross-component integration tests
- **hindsight-dev/**: Development tools and benchmarks

### Core Engine (hindsight-api-slim/hindsight_api/engine/)
- `memory_engine.py`: Main orchestrator for retain/recall/reflect operations
- `llm_wrapper.py`: LLM abstraction supporting OpenAI, Anthropic, Gemini, VertexAI, Groq, MiniMax, Ollama, LM Studio, LiteLLM, Claude Code
- `embeddings.py`: Embedding generation (local sentence-transformers or TEI)
- `cross_encoder.py`: Reranking (local or TEI)
- `entity_resolver.py`: Entity extraction and normalization
- `query_analyzer.py`: Query intent analysis

**retain/**: Memory ingestion pipeline
- `orchestrator.py`: Coordinates the retain flow
- `fact_extraction.py`: LLM-based fact extraction from content
- `link_utils.py`: Entity link creation and management

**search/**: Multi-strategy retrieval
- `retrieval.py`: Main retrieval orchestrator
- `graph_retrieval.py`: Graph retrieval abstract base class
- `link_expansion_retrieval.py`: Link expansion graph retrieval
- `fusion.py`: Reciprocal rank fusion for combining results
- `reranking.py`: Cross-encoder reranking
- `recall_cache.py`: MemSense recall result cache (Tier 0 exact + Tier 1 fuzzy Jaccard)

### API Layer (hindsight-api-slim/hindsight_api/api/)
- `http.py`: FastAPI HTTP routers for all REST endpoints
- `mcp.py`: Model Context Protocol server implementation

Main operations:
- **Retain**: Store memories, extracts facts/entities/relationships
- **Recall**: Retrieve memories via 4 parallel strategies (semantic, BM25, graph, temporal) + reranking
- **Reflect**: Disposition-aware reasoning using memories and mental models.

### Database
PostgreSQL with pgvector. Schema managed via Alembic migrations in `hindsight-api-slim/hindsight_api/alembic/`. Migrations run automatically on API startup.

Key tables: `banks`, `memory_units`, `documents`, `entities`, `entity_links`

### Adding Database Migrations

1. **Create a new migration file** in `hindsight-api-slim/hindsight_api/alembic/versions/`:
   - File name format: `<revision_id>_<description>.py` (e.g., `f1a2b3c4d5e6_add_new_index.py`)
   - Use a unique hex revision ID (12 chars)
   - Set `down_revision` to the previous migration's revision ID

2. **Migration template**:
   ```python
   """Description of the migration

   Revision ID: f1a2b3c4d5e6
   Revises: <previous_revision_id>
   Create Date: YYYY-MM-DD
   """
   from collections.abc import Sequence
   from alembic import context, op

   revision: str = "f1a2b3c4d5e6"
   down_revision: str | Sequence[str] | None = "<previous_revision_id>"
   branch_labels: str | Sequence[str] | None = None
   depends_on: str | Sequence[str] | None = None

   def _get_schema_prefix() -> str:
       """Get schema prefix for table names (required for multi-tenant support)."""
       schema = context.config.get_main_option("target_schema")
       return f'"{schema}".' if schema else ""

   def upgrade() -> None:
       schema = _get_schema_prefix()
       op.execute(f"CREATE INDEX ... ON {schema}table_name(...)")

   def downgrade() -> None:
       schema = _get_schema_prefix()
       op.execute(f"DROP INDEX IF EXISTS {schema}index_name")
   ```

3. **Run migrations locally**:
   ```bash
   # Set database URL and run migrations for the base schema plus all tenants
   uv run hindsight-admin run-db-migration

   # Run on a specific tenant schema
   uv run hindsight-admin run-db-migration --schema tenant_xyz
   ```

## Key Conventions

### Code Quality

**Before writing code, read `.claude/skills/code-review/SKILL.md`** for the full coding standards (Python style, type safety, TypeScript style, general principles).

**Always run the lint script after making Python or TypeScript/Node changes:**
```bash
./scripts/hooks/lint.sh
```

**After completing any implementation work, run `/code-review`** to verify your changes against project standards (missing tests, dead code, type safety, etc.). Fix any "must fix" issues before considering the task done.

**MANDATORY: Run `/code-review` before pushing code or creating a pull request.** Do not push or create a PR until all "must fix" issues are resolved.

### Memory Banks
- Each bank is an isolated memory store (like a "brain" for one user/agent)
- Banks have dispositions (skepticism, literalism, empathy traits 1-5) affecting reflect
- Banks can have background context
- Bank isolation is strict - no cross-bank data leakage

### API Design
- All endpoints operate on a single bank per request
- Multi-bank queries are client responsibility to orchestrate
- Disposition traits only affect reflect, not recall

### Control Plane API Routes

When adding or modifying parameters in the dataplane API (hindsight-api), you must also update the control plane routes that proxy to it:

1. **API Routes** (`hindsight-control-plane/src/app/api/`):
   - `recall/route.ts` - proxies to `/v1/default/banks/{bank_id}/memories/recall`
   - `reflect/route.ts` - proxies to `/v1/default/banks/{bank_id}/reflect`
   - `memories/retain/route.ts` - proxies to `/v1/default/banks/{bank_id}/memories/retain`
   - Other routes follow the same pattern

2. **Client types** (`hindsight-control-plane/src/lib/api.ts`):
   - Update the TypeScript type definitions for `recall()`, `reflect()`, `retain()` etc.

3. **Checklist when adding new API parameters**:
   - Add parameter extraction in the route handler (destructure from `body`)
   - Pass the parameter to the SDK call
   - Update the client type definition in `lib/api.ts`
   - Update any UI components that need to use the new parameter

### Adding New Integrations

Every new integration in `hindsight-integrations/` must satisfy all of the following before it can be merged:

1. **Tests are required** — tests must simulate or exercise the external system (mock the framework's interfaces and verify the integration actually calls Hindsight correctly). Pure unit tests of helper functions are not sufficient.
2. **CI job** — add a test job in `.github/workflows/test.yml` following the existing pattern (e.g., `test-crewai-integration`). The job must build, install deps, and run `uv run pytest tests -v`. Also add the integration to `detect-changes` outputs so it only runs when its files change.
3. **Release process** — add the integration name to the `VALID_INTEGRATIONS` array in `scripts/release-integration.sh` so it can be released via the standard release workflow.
4. **Follow project code standards** — Python style, type safety, no raw dicts for structured data, no multi-item tuple returns (see `.claude/skills/code-review/SKILL.md`).

If any of these are missing, the integration is incomplete and must not be pushed or merged.

### Changelogs

Never add "Unreleased" entries to changelogs (e.g. `hindsight-docs/src/pages/changelog/**`). Changelog entries are written by the release script (`./scripts/release-integration.sh`) when a version is actually cut. If a bug fix or feature needs documenting before release, describe it in the PR/commit — the release tooling will surface it in the published changelog section.

### Adding New API Configuration Flags

Configuration follows a hierarchical system: **Global (env vars) → Tenant (via extension) → Bank (database)**.

Fields must be categorized as either **hierarchical** (can be overridden per-tenant/bank) or **static** (server-level only).

#### Adding a New Configuration Field

1. **config.py** (`hindsight-api-slim/hindsight_api/config.py`):
   - Add `ENV_*` constant for the environment variable name (e.g., `ENV_MY_SETTING = "HINDSIGHT_API_MY_SETTING"`)
   - Add `DEFAULT_*` constant for the default value
   - Add field to `HindsightConfig` dataclass with type annotation
   - **Mark as configurable** by adding to `_CONFIGURABLE_FIELDS` set if the field should be overridable per-tenant/bank via API
   - Add initialization in `from_env()` method

   ```python
   # Configurable field (can be overridden per-tenant/bank via API)
   _CONFIGURABLE_FIELDS = {
       ...,
       "my_setting",  # Add here for configurable
   }

   # Static field - just don't add to _CONFIGURABLE_FIELDS
   ```

2. **main.py** (`hindsight-api-slim/hindsight_api/main.py`):
   - Add field to the manual `HindsightConfig()` constructor call (search for "CLI override")

3. **Use hierarchical config in MemoryEngine**:
   ```python
   # Config is resolved automatically per bank via ConfigResolver
   config_dict = await self._config_resolver.get_bank_config(bank_id, context)
   value = config_dict["my_setting"]
   ```

4. **Use static config** (non-hierarchical):
   ```python
   from ...config import get_config
   config = get_config()
   value = config.my_static_field
   ```

5. **Documentation** (`hindsight-docs/docs/developer/configuration.md`):
   - Add to appropriate section table with Variable, Description, Default
   - Mark if it's hierarchical (can be overridden per-bank)

#### Hierarchical vs Static Guidelines

**Hierarchical** (per-bank overridable):
- LLM settings (provider, model, API key, base URL)
- Operation-specific settings (retain mode, chunk size, etc.)
- Feature flags that vary by customer/bank

**Static** (server-level only):
- Infrastructure settings (database URL, port, host)
- Global limits (max concurrent operations)
- System-wide feature flags

### Git Hooks

Set up pre-commit hooks to auto-lint before each commit:
```bash
./scripts/setup-hooks.sh
```
This runs Python (ruff check/format, ty check) and TypeScript (eslint, prettier) linting in parallel on commit.

### Release Process

Releases are managed via `scripts/release.sh <version>`, which bumps versions across all components, regenerates OpenAPI spec and client SDKs, updates docs versioning, creates a git tag, and pushes. During development, do NOT manually regenerate clients — that only happens during releases.

For individual integrations: `scripts/release-integration.sh`.

## Environment Setup

```bash
cp .env.example .env
# Edit .env with LLM API key

# Python deps
uv sync --directory hindsight-api-slim/

# Node deps (uses npm workspaces)
npm install
```

Required env vars:
- `HINDSIGHT_API_LLM_PROVIDER`: openai, anthropic, gemini, groq, minimax, ollama, lmstudio
- `HINDSIGHT_API_LLM_API_KEY`: Your API key
- `HINDSIGHT_API_LLM_MODEL`: Model name (e.g., gpt-4o-mini, claude-sonnet-4-20250514)

Optional (uses local models by default):
- `HINDSIGHT_API_EMBEDDINGS_PROVIDER`: local (default) or tei
- `HINDSIGHT_API_RERANKER_PROVIDER`: local (default) or tei
- `HINDSIGHT_API_DATABASE_URL`: External PostgreSQL (uses embedded pg0 by default)
- `HINDSIGHT_API_ENABLE_BANK_CONFIG_API`: Enable per-bank config API (default: true)

MemSense recall cache (disabled by default):
- `HINDSIGHT_API_RECALL_CACHE_ENABLED`: Enable in-memory recall cache (default: false)
- `HINDSIGHT_API_RECALL_CACHE_MAX_SIZE`: LRU cache capacity (default: 256)
- `HINDSIGHT_API_RECALL_CACHE_TTL_SECONDS`: Cache entry TTL (default: 300)
- `HINDSIGHT_API_RECALL_CACHE_FUZZY_THRESHOLD`: Jaccard similarity threshold for fuzzy matching (default: 0.7, set 0 to disable fuzzy)
- `HINDSIGHT_API_RECALL_CACHE_REDIS_URL`: Optional Redis URL (e.g. `redis://localhost:6379/0`). When set, Tier 0 exact-match results are shared across replicas; requires `pip install memsense-api-slim[cache-redis]`.

MemSense retain enrichment (disabled by default):
- `HINDSIGHT_API_RETAIN_POST_EXTRACTION_ENABLED`: Enable date correction + detail preservation (default: false)
- `HINDSIGHT_API_RETAIN_FACT_FORMAT_CLEAN_ENABLED`: Strip metadata suffixes from fact text (default: false)
- `HINDSIGHT_API_RETAIN_PII_REDACT_ENABLED`: Redact email/phone/SSN/credit-card/IP patterns in extracted facts (default: false)
- `HINDSIGHT_API_RETAIN_MISSION`: Custom instructions for fact extraction (see ingest-locomo.sh for recommended LoCoMo mission)

MemSense compliance + usage endpoints (disabled by default):
- `HINDSIGHT_API_ERASURE_API_ENABLED`: Expose `POST /v1/default/banks/{bank_id}/erase` (GDPR-style erase, emits `gdpr_erase` audit entry; `drop_bank=true` also removes bank shell)
- `HINDSIGHT_API_USAGE_API_ENABLED`: Expose `GET /v1/default/usage` (tenant-wide token-usage aggregation over an arbitrary time window, grouped by operation / bank / day)
