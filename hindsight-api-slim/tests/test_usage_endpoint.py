"""Unit tests for the MemSense tenant-wide usage endpoint.

Mocks ``app.state.memory._get_pool`` so tests run without a real database.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hindsight_api.api.memsense_routes import register_memsense_routes
from hindsight_api.api.usage import register_usage_route
from hindsight_api.config import clear_config_cache


def _make_pool(rows: list[dict]):
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=rows)

    @asynccontextmanager
    async def _acquire():
        yield conn

    pool = MagicMock()
    pool.acquire = lambda: _acquire()
    return pool, conn


def _build_app(rows: list[dict] | None = None) -> tuple[FastAPI, MagicMock]:
    app = FastAPI()
    memory = MagicMock()
    pool, conn = _make_pool(rows or [])
    memory._get_pool = AsyncMock(return_value=pool)
    app.state.memory = memory
    return app, conn


def test_usage_groups_by_operation():
    rows = [
        {
            "group_key": "retain",
            "operation_count": 3,
            "llm_input_tokens": 100,
            "llm_output_tokens": 50,
            "context_tokens": 0,
            "saved_tokens": 0,
        },
        {
            "group_key": "recall",
            "operation_count": 7,
            "llm_input_tokens": 0,
            "llm_output_tokens": 0,
            "context_tokens": 1400,
            "saved_tokens": 200,
        },
    ]
    app, conn = _build_app(rows)
    register_usage_route(app)
    client = TestClient(app)

    resp = client.get("/v1/default/usage?group_by=operation")
    assert resp.status_code == 200
    body = resp.json()

    assert body["group_by"] == "operation"
    assert body["total_operations"] == 10
    assert body["totals"]["llm_input_tokens"] == 100
    assert body["totals"]["llm_output_tokens"] == 50
    assert body["totals"]["context_tokens"] == 1400
    assert body["totals"]["saved_tokens"] == 200
    groups = {g["group"]: g for g in body["groups"]}
    assert groups["retain"]["operation_count"] == 3
    assert groups["recall"]["context_tokens"] == 1400

    # SQL was called with a default ~30-day window (args: query, start, end, bank_id)
    called_args = conn.fetch.await_args.args
    assert called_args[3] is None  # bank_id filter not set


def test_usage_respects_bank_id_filter():
    app, conn = _build_app([])
    register_usage_route(app)
    client = TestClient(app)

    resp = client.get("/v1/default/usage?bank_id=bank-42&group_by=operation")
    assert resp.status_code == 200
    args = conn.fetch.await_args.args
    assert args[3] == "bank-42"


def test_usage_validates_start_before_end():
    app, _ = _build_app([])
    register_usage_route(app)
    client = TestClient(app)

    resp = client.get("/v1/default/usage?start=2026-04-10T00:00:00Z&end=2026-04-01T00:00:00Z&group_by=operation")
    assert resp.status_code == 400
    assert "strictly before" in resp.json()["detail"]


def test_usage_group_by_day_formats_row_keys_as_iso_date():
    rows = [
        {
            "group_key": "2026-04-10",
            "operation_count": 2,
            "llm_input_tokens": 10,
            "llm_output_tokens": 5,
            "context_tokens": 0,
            "saved_tokens": 0,
        },
    ]
    app, _ = _build_app(rows)
    register_usage_route(app)
    client = TestClient(app)

    resp = client.get("/v1/default/usage?group_by=day")
    assert resp.status_code == 200
    body = resp.json()
    assert body["groups"][0]["group"] == "2026-04-10"


def test_usage_rejects_invalid_group_by():
    app, _ = _build_app([])
    register_usage_route(app)
    client = TestClient(app)

    resp = client.get("/v1/default/usage?group_by=hour")
    # FastAPI validates the Literal and returns 422
    assert resp.status_code == 422


def test_dispatcher_noop_when_flag_off():
    app, _ = _build_app([])
    os.environ.pop("HINDSIGHT_API_USAGE_API_ENABLED", None)
    clear_config_cache()
    register_memsense_routes(app)
    client = TestClient(app)

    resp = client.get("/v1/default/usage?group_by=operation")
    assert resp.status_code == 404


def test_dispatcher_registers_when_flag_on():
    app, _ = _build_app([])
    os.environ["HINDSIGHT_API_USAGE_API_ENABLED"] = "true"
    clear_config_cache()
    try:
        register_memsense_routes(app)
        client = TestClient(app)
        resp = client.get("/v1/default/usage?group_by=operation")
        assert resp.status_code == 200
    finally:
        os.environ.pop("HINDSIGHT_API_USAGE_API_ENABLED", None)
        clear_config_cache()


def test_usage_uses_explicit_start_end_when_provided():
    app, conn = _build_app([])
    register_usage_route(app)
    client = TestClient(app)

    resp = client.get(
        "/v1/default/usage?start=2026-04-01T00:00:00%2B00:00&end=2026-04-15T00:00:00%2B00:00&group_by=operation"
    )
    assert resp.status_code == 200
    args = conn.fetch.await_args.args
    assert args[1] == datetime(2026, 4, 1, tzinfo=timezone.utc)
    assert args[2] == datetime(2026, 4, 15, tzinfo=timezone.utc)
