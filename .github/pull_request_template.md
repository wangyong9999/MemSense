## Summary

<!-- Brief description of what this PR does and why -->

## Changes

- 

## Quality Checklist

- [ ] New/modified functions have type annotations
- [ ] New files have corresponding `test_*.py`
- [ ] `uv run ruff check .` passes (in `hindsight-api-slim/`)
- [ ] `uv run ruff format --check .` passes (in `hindsight-api-slim/`)
- [ ] `uv run pytest tests/ -v` passes (in `hindsight-api-slim/`)
- [ ] If modifying recall path: mini-benchmark shows no precision regression
- [ ] If modifying API endpoints: OpenAPI spec regenerated (`./scripts/generate-openapi.sh`)
- [ ] If modifying schema: Alembic migration has both `upgrade()` and `downgrade()`
- [ ] If modifying config: `.env.example` and docs updated

## Test Plan

<!-- How was this tested? -->

- 
