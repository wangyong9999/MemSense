# Release pipeline alignment — MemSense fork checklist

Everything you need to set up so `release.yml`, `release-integration.yml`, `test.yml`, and `deploy-docs.yml` work on `wangyong9999/MemSense` the same way they work on `vectorize-io/hindsight`.

Treat this as a living checklist. Tick items as you complete them.

---

## 1 — PyPI publishing

Goal: `git push origin vX.Y.Z` publishes Python wheels to PyPI under the `memsense-*` namespace.

### 1.1 Account

- [x] Register a PyPI account — **username: `wangyong9999`**
- [ ] Enable 2FA on that account (required by PyPI for publishing in most cases)

### 1.2 Package names + Pending Publishers

Package rename mapping:

| Current (upstream) | Our PyPI name | Pending Publisher created |
|---|---|---|
| `hindsight-api-slim` | `memsense-api-slim` | ✅ |
| `hindsight-api` | `memsense-api` | ☐ |
| `hindsight-all-slim` | `memsense-all-slim` | ☐ |
| `hindsight-all` | `memsense-all` | ☐ |
| `hindsight-embed` | `memsense-embed` | ☐ |
| `hindsight-client` | `memsense-client` | ☐ |
| `hindsight-dev` | not published | N/A |

For each row above with ☐, do:

1. Go to https://pypi.org/manage/account/publishing/
2. **Add a new pending publisher**, fill:
   - Project name: `memsense-<name>`
   - Owner: `wangyong9999`
   - Repository name: `MemSense`
   - Workflow name: `release.yml`
   - Environment name: `pypi`
3. Submit.

### 1.3 GitHub environment

- [ ] https://github.com/wangyong9999/MemSense/settings/environments → **New environment** named `pypi`
  - No secret needed (trusted publishing uses OIDC)
  - Optional: restrict deployment branches to `main` + tag pattern `v*`

---

## 2 — npm publishing

Goal: `git push origin vX.Y.Z` publishes TypeScript packages under `@memsense/*` scope.

### 2.1 Account + scope

- [ ] Register npm account at https://www.npmjs.com/signup + enable 2FA
- [ ] Create organization `memsense` at https://www.npmjs.com/org/create (free plan is fine for public packages)
- [ ] Your npm username: ________________

### 2.2 Package name mapping

| Upstream npm name | Our npm name |
|---|---|
| `@vectorize-io/hindsight-client` | `@memsense/hindsight-client` |
| `@vectorize-io/hindsight-control-plane` | `@memsense/hindsight-control-plane` |
| `@vectorize-io/hindsight-all` | `@memsense/hindsight-all` |

(Integration scope — see §5 below.)

### 2.3 Automation Token

- [ ] https://www.npmjs.com/settings/<your-username>/tokens → **Generate New Token** → **Granular Access Token**
  - Expiration: 1 year
  - Packages and scopes: `@memsense` read+write
  - Organizations: `memsense` read+write
  - Copy the token (shown once).

### 2.4 GitHub environment + secret

- [ ] Create environment `npm` at https://github.com/wangyong9999/MemSense/settings/environments
- [ ] In the `npm` environment → **Add secret** → Name `NPM_TOKEN`, value = token from 2.3
- [ ] Optional: restrict deployment branches to `main` + tag pattern `v*`

---

## 3 — GitHub repo settings

### 3.1 Actions permissions

- [ ] https://github.com/wangyong9999/MemSense/settings/actions
  - **Workflow permissions** → ✅ **Read and write permissions**
  - ✅ **Allow GitHub Actions to create and approve pull requests** (for Dependabot auto-merge)

### 3.2 Pages (docs site)

- [ ] https://github.com/wangyong9999/MemSense/settings/pages
  - **Source** → **GitHub Actions**
  - Docs URL after first push: https://wangyong9999.github.io/MemSense/
  - (Optional) Custom domain: add CNAME → `wangyong9999.github.io` in DNS

### 3.3 GHCR visibility (after first release push)

The release workflow pushes 5 Docker images + 1 Helm chart to GHCR. By default they land **private**. To make public:

- [ ] https://github.com/users/wangyong9999/packages — find each of:
  - `hindsight-api`
  - `hindsight-api-slim`
  - `hindsight` (standalone + `-slim` variant as tags on same image)
  - `hindsight-control-plane`
  - `hindsight` (helm chart — different package type from image)
- [ ] For each: **Package settings** → **Change visibility** → **Public**
- [ ] Same page → **Manage Actions access** → **Add `MemSense` with `write` role**

Note: image names are still `hindsight-*` (we don't rebrand images for merge friendliness). If you later decide to rebrand images to `memsense-*`, change the `image_name` in `release.yml` matrix and expect future upstream merges to conflict on those lines.

---

## 4 — Optional: LLM / cloud test secrets

`test.yml` runs integration tests that hit real LLM / cloud APIs. Upstream has these secrets configured; **on our fork they’re not needed** unless you want PRs to trigger full paid integration tests.

| Secret | Used by | Recommendation |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI provider integration tests | skip |
| `GEMINI_API_KEY` | Gemini provider tests | skip |
| `GROQ_API_KEY` | Groq provider + Docker smoke test | skip |
| `COHERE_API_KEY` | Cohere reranker tests | skip |
| `GCP_VERTEXAI_CREDENTIALS` | VertexAI tests (service-account JSON) | skip |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION_NAME` | Bedrock + S3 file-storage tests | skip |

If you do want them, add as repository secrets at https://github.com/wangyong9999/MemSense/settings/secrets/actions.

---

## 5 — Integration publishing (17 framework integrations)

Triggered by tags like `integrations/litellm/v0.1.0`. Upstream publishes:

- **Python (11)**: ag2, agno, autogen, codex, crewai, hermes, langgraph, litellm, llamaindex, pydantic-ai, strands, openai-agents
- **TypeScript (5)**: ai-sdk, chat, nemoclaw, openclaw, paperclip
- **Plugin (1)**: claude-code (via Claude Plugin Marketplace; no external registry)

### If you want to publish integrations from our fork

Each Python integration needs:
- [ ] PyPI Pending Publisher under name `memsense-<integration>` (same workflow/owner/repo, `environment=pypi`)
- [ ] Rename `hindsight-integrations/<name>/pyproject.toml` `name` field to `memsense-<integration>`

Each TypeScript integration needs:
- [ ] Rename `package.json` `name` to `@memsense/hindsight-<integration>`
- [ ] NPM_TOKEN already covers them (same `@memsense` scope)

Claude Code plugin:
- Nothing to register externally.
- Users install via `claude plugin marketplace add wangyong9999/MemSense --sparse hindsight-integrations`.

**Recommendation**: skip integration publishing until v0.6 or until specific integration is requested.

---

## 6 — Documentation customization

### 6.1 Umami analytics (optional)

`deploy-docs.yml` uses `UMAMI_WEBSITE_ID` secret. Without it, docs deploy fine but without visit tracking.

- [ ] Skip, or register at https://umami.is and add the secret.

### 6.2 Docs URL / custom domain

`hindsight-docs/docusaurus.config.ts` hardcodes `https://hindsight.vectorize.io`. If you serve docs from your own domain:

- [ ] Pick domain (e.g. `docs.memsense.io`)
- [ ] Update `url` + `baseUrl` in `docusaurus.config.ts`
- [ ] Configure Pages custom domain + DNS
- Note: this file is upstream-tracked; every `sync-upstream.sh` will need to re-apply these 2 lines. Keep the manual diff tiny.

---

## Status matrix

| Area | Needed for v0.5.4? | Needed for integrations? | Status |
|---|---|---|---|
| PyPI account + 1st Pending Publisher | optional (only for memsense-api-slim publish) | yes | username = wangyong9999 ✅; 1/6 Pending Publishers ✅ |
| PyPI remaining 5 Pending Publishers | optional | yes | pending |
| `pypi` GitHub environment | yes (even with 1 package) | yes | pending |
| npm account + `@memsense` scope | no | yes | pending |
| NPM_TOKEN in `npm` environment | no | yes | pending |
| Actions → Read and write | yes (GHCR push needs it) | yes | pending verify |
| Pages → Source = GitHub Actions | yes (docs) | no | pending |
| GHCR visibility Public | optional | optional | post-first-release |
| LLM test secrets | no | no | skip |
| Umami website ID | no | no | skip |
| Custom docs domain | no | no | skip until v0.6 |

---

## Gotchas observed so far

- **PyPI package name vs Python import name**: we keep import name as `hindsight_api` (upstream unchanged) but publish as `memsense-api-slim`. Users do `pip install memsense-api-slim` and `import hindsight_api`. Same pattern as `beautifulsoup4` / `bs4`.
- **Image names**: we keep Docker image names as `hindsight-*` in GHCR for the same reason. Only the owner namespace differs (`ghcr.io/wangyong9999/hindsight-api` vs `ghcr.io/vectorize-io/hindsight-api`).
- **Trusted publishing**: first publish to PyPI for a new name creates the project under your account. No placeholder upload needed.
- **release.yml gate**: currently `if: github.repository == 'vectorize-io/hindsight'` skips all PyPI/npm jobs on fork. Once Pending Publishers + NPM_TOKEN are in place, the gate becomes `|| github.repository == 'wangyong9999/MemSense'` and jobs run on our fork too.
