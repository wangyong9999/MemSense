"""Unit tests for the MemSense GDPR erase endpoint.

Runs without a database or real MemoryEngine — ``app.state.memory`` is a
mock whose ``delete_bank`` returns a canned counts dict, letting the
tests focus on route registration, flag gating, audit emission, and
response shape.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hindsight_api.api.erasure import ErasureResponse, register_erasure_route
from hindsight_api.api.memsense_routes import register_memsense_routes
from hindsight_api.config import clear_config_cache


def _build_app(memory_delete_result: dict | None = None) -> tuple[FastAPI, MagicMock, MagicMock]:
    app = FastAPI()
    memory = MagicMock()
    memory.delete_bank = AsyncMock(
        return_value=memory_delete_result
        or {
            "memory_units_deleted": 5,
            "entities_deleted": 2,
            "documents_deleted": 1,
        }
    )
    audit_logger = MagicMock()
    audit_logger.log_fire_and_forget = MagicMock()
    app.state.memory = memory
    app.state.audit_logger = audit_logger
    return app, memory, audit_logger


def test_erase_endpoint_response_shape():
    app, memory, audit = _build_app()
    register_erasure_route(app)
    client = TestClient(app)

    resp = client.post("/v1/default/banks/my-bank/erase")

    assert resp.status_code == 200
    body = resp.json()
    parsed = ErasureResponse(**body)
    assert parsed.success is True
    assert parsed.bank_id == "my-bank"
    assert parsed.memory_units_deleted == 5
    assert parsed.entities_deleted == 2
    assert parsed.documents_deleted == 1
    assert parsed.bank_dropped is False
    memory.delete_bank.assert_awaited_once()
    call_kwargs = memory.delete_bank.await_args.kwargs
    assert call_kwargs["delete_bank_profile"] is False


def test_erase_with_drop_bank_passes_flag_through():
    app, memory, _ = _build_app()
    register_erasure_route(app)
    client = TestClient(app)

    resp = client.post("/v1/default/banks/my-bank/erase?drop_bank=true")
    assert resp.status_code == 200
    assert resp.json()["bank_dropped"] is True
    assert memory.delete_bank.await_args.kwargs["delete_bank_profile"] is True


def test_erase_emits_gdpr_audit_entry():
    app, _, audit = _build_app()
    register_erasure_route(app)
    client = TestClient(app)

    client.post("/v1/default/banks/my-bank/erase")

    audit.log_fire_and_forget.assert_called_once()
    entry = audit.log_fire_and_forget.call_args.args[0]
    assert entry.action == "gdpr_erase"
    assert entry.bank_id == "my-bank"
    assert entry.transport == "http"
    assert entry.request == {"drop_bank": False}


def test_erase_surfaces_500_on_engine_failure():
    app, memory, _ = _build_app()
    memory.delete_bank = AsyncMock(side_effect=RuntimeError("boom"))
    register_erasure_route(app)
    client = TestClient(app)

    resp = client.post("/v1/default/banks/my-bank/erase")
    assert resp.status_code == 500
    assert "boom" in resp.json()["detail"]


def test_dispatcher_noop_when_flag_off():
    app, _, _ = _build_app()
    os.environ.pop("HINDSIGHT_API_ERASURE_API_ENABLED", None)
    clear_config_cache()
    register_memsense_routes(app)
    client = TestClient(app)

    resp = client.post("/v1/default/banks/my-bank/erase")
    assert resp.status_code == 404


def test_dispatcher_registers_when_flag_on():
    app, _, _ = _build_app()
    os.environ["HINDSIGHT_API_ERASURE_API_ENABLED"] = "true"
    clear_config_cache()
    try:
        register_memsense_routes(app)
        client = TestClient(app)
        resp = client.post("/v1/default/banks/my-bank/erase")
        assert resp.status_code == 200
    finally:
        os.environ.pop("HINDSIGHT_API_ERASURE_API_ENABLED", None)
        clear_config_cache()


@pytest.mark.parametrize("authorization_header", ["Bearer sk-abc", "sk-abc", ""])
def test_erase_accepts_various_auth_header_formats(authorization_header):
    app, _, _ = _build_app()
    register_erasure_route(app)
    client = TestClient(app)

    headers = {"Authorization": authorization_header} if authorization_header else {}
    resp = client.post("/v1/default/banks/my-bank/erase", headers=headers)
    assert resp.status_code == 200
