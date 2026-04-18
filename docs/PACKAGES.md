# Package layout

The repo ships **four Python distribution packages** that look very similar by name. This document explains what each one actually contains, when to use which, and why the layout exists.

## TL;DR

| PyPI name | MemSense name | Contains | Install for |
|---|---|---|---|
| `hindsight-api-slim` | `memsense-api-slim` | Full API server code (FastAPI, MemoryEngine, workers, alembic migrations, CLI entry points). No bundled ML models. | Running the API with external embedding/reranker services (TEI, OpenAI, Cohere, etc.). |
| `hindsight-api` | `memsense-api` | Depends on `hindsight-api-slim[all]` + `hindsight-embed`. | Single-machine setup where you want the API plus local CPU-based embedding/reranker models bundled. |
| `hindsight-all-slim` | `memsense-all-slim` | Depends on `hindsight-api-slim`, `hindsight-client`, `hindsight-embed`. Thin meta-package. | Embedding Hindsight into a larger Python app — import the API, client, and embedding models without running a server. |
| `hindsight-all` | `memsense-all` | Depends on `hindsight-api-slim[all]`, `hindsight-client`, `hindsight-embed`. Also provides a convenience `start_server()` Python API for programmatic launches. | Same as `-all-slim` but with local ML models enabled by default. |

Short version: **the only package with actual code is `hindsight-api-slim`** (≈122 kLOC). The other three are dependency aggregators that re-export or thinly wrap it so `pip install`ers can pick the right bundle for their use case.

## Dependency graph

```
                         +-------------------------+
                         |  hindsight-api-slim     |   ← real implementation
                         |  (FastAPI server,       |
                         |   MemoryEngine,         |
                         |   alembic, worker,      |
                         |   CLI)                  |
                         +-------------------------+
                              ▲         ▲        ▲
                              |         |        |
                              |         |  +-------------------+
                              |         |  |  hindsight-embed  | ← local ML models
                              |         |  |  (sentence-       |
                              |         |  |   transformers,   |
                              |         |  |   cross-encoder)  |
                              |         |  +-------------------+
                              |         |        ▲
        +-------------+       |         |        |
        |  hindsight- |       |   +--------------+
        |  client     |   +---+   |
        |  (Python    |   |       |
        |  SDK)       |   |       |
        +-------------+   |       |
              ▲           |       |
              |           |       |
        +-----+-----------+-------+---+      +---------------------+
        |  hindsight-all-slim         |      |  hindsight-all      |
        |  (slim+client+embed)        |      |  (slim+client+embed |
        +-----------------------------+      |   +local ML extras) |
                                             +---------------------+
```

## Why four packages

Historical reason: different deployment shapes need different heavy dependencies.

1. **Running the server in a container** where embedding/reranker come from TEI or a managed API (OpenAI, Cohere) → you only need the server code. Installing torch + sentence-transformers for those users is wasted ~2 GB of image size. → `memsense-api-slim`.

2. **Single-machine self-hosted** where the user wants "one `pip install` and it just works" with local ML models → `memsense-api`.

3. **Embedding into a larger Python app** where you want the `hindsight_client` SDK alongside the engine (e.g. in a notebook, a Celery task, a different web framework) → `memsense-all-slim` or `memsense-all`.

Renaming or consolidating these packages looks tempting — the naming is genuinely confusing — but:

- Upstream `vectorize-io/hindsight` ships the same 4 packages. Our fork keeps the directory layout and dependency structure identical so upstream merges stay mechanical.
- PyPI users who `pip install hindsight-api-slim` today get a working install; renaming would break them. On our fork we use `memsense-*` from day one, avoiding that problem.

## Import name stays `hindsight_api`

Users install `memsense-api-slim` but import `hindsight_api`:

```python
# pip install memsense-api-slim
from hindsight_api import ...        # <-- unchanged
from hindsight_api.engine import MemoryEngine
```

This follows the `pip install beautifulsoup4` / `import bs4` pattern. Keeping the import name upstream-aligned means our fork's code diff against upstream stays tiny — any future `git merge upstream/main` won't conflict on thousands of import statements.

## Choosing a package

| You are… | Install |
|---|---|
| Running the server behind a load balancer, embeddings delegated to TEI or a cloud provider | `memsense-api-slim` |
| Running on a dev laptop or single VM and want local ML models out of the box | `memsense-api` |
| Writing a Python script/notebook that embeds Hindsight rather than running it as a separate service | `memsense-all-slim` (or `memsense-all` if you also want local ML) |
| Writing a client that talks to a remote Hindsight server | `memsense-client` |

## Cross-reference

- Dependency sources: see each package’s `pyproject.toml` `dependencies` and `[project.optional-dependencies]` sections.
- Release flow: see `scripts/release.sh` which bumps all four versions together, and `.github/workflows/release.yml` which publishes them in order (client → slim → api/all wrappers).
- Fork-specific release alignment: see [`hindsight-dev/planning/RELEASE_ALIGNMENT.md`](../hindsight-dev/planning/RELEASE_ALIGNMENT.md).
