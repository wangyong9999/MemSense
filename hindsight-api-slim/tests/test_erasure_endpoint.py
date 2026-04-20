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
    """5xx detail is opaque — exception message never surfaces to caller."""
    app, memory, _ = _build_app()
    memory.delete_bank = AsyncMock(side_effect=RuntimeError("boom /etc/secrets"))
    register_erasure_route(app)
    client = TestClient(app)

    resp = client.post("/v1/default/banks/my-bank/erase")
    assert resp.status_code == 500
    detail = resp.json()["detail"]
    assert "boom" not in detail
    assert "/etc/secrets" not in detail
    assert detail.startswith("internal error (ref: ")


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


# ===========================================================================
# Memory-lifecycle hardening
# ===========================================================================


def test_erase_is_idempotent_on_already_empty_bank():
    """Erasing an empty bank returns 200 with zero counts — compliance idempotence."""
    empty = {"memory_units_deleted": 0, "entities_deleted": 0, "documents_deleted": 0}
    app, memory, _ = _build_app(memory_delete_result=empty)
    register_erasure_route(app)
    client = TestClient(app)

    for _ in range(3):
        resp = client.post("/v1/default/banks/bz/erase")
        assert resp.status_code == 200
        body = resp.json()
        assert body["memory_units_deleted"] == 0
        assert body["success"] is True

    assert memory.delete_bank.await_count == 3


def test_erase_forwards_authentication_error_as_401():
    """AuthenticationError from delete_bank must bubble up (upstream maps it)."""
    from hindsight_api.extensions import AuthenticationError

    app, memory, _ = _build_app()
    memory.delete_bank = AsyncMock(side_effect=AuthenticationError("no key"))
    register_erasure_route(app)

    # Install the app's upstream-style exception handler.
    from starlette.responses import JSONResponse

    @app.exception_handler(AuthenticationError)
    async def _handler(request, exc):
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    client = TestClient(app)
    resp = client.post("/v1/default/banks/bz/erase")
    assert resp.status_code == 401


@pytest.mark.xfail(
    reason="On delete_bank exception the audit entry is never emitted. Compliance "
    "requires a 'gdpr_erase_failed' record regardless of success. See "
    "FIX_PLAN_HARDENING.md §3.",
    strict=True,
)
def test_erase_emits_audit_entry_even_on_failure():
    app, memory, audit = _build_app()
    memory.delete_bank = AsyncMock(side_effect=RuntimeError("disk full"))
    register_erasure_route(app)
    client = TestClient(app)

    resp = client.post("/v1/default/banks/bz/erase")
    assert resp.status_code == 500
    audit.log_fire_and_forget.assert_called_once()
    entry = audit.log_fire_and_forget.call_args.args[0]
    assert entry.action in ("gdpr_erase_failed", "gdpr_erase")
    assert entry.bank_id == "bz"


def test_erase_drop_bank_true_removes_bank_shell():
    """drop_bank=true sets delete_bank_profile=True on the engine call."""
    app, memory, _ = _build_app()
    register_erasure_route(app)
    client = TestClient(app)

    resp = client.post("/v1/default/banks/bz/erase?drop_bank=true")
    assert resp.status_code == 200
    assert memory.delete_bank.await_args.kwargs["delete_bank_profile"] is True


def test_erase_does_not_expose_internal_traceback():
    """5xx responses must not leak stack traces to the caller."""
    app, memory, _ = _build_app()
    memory.delete_bank = AsyncMock(side_effect=RuntimeError("internal path /etc/secrets"))
    register_erasure_route(app)
    client = TestClient(app)

    resp = client.post("/v1/default/banks/bz/erase")
    assert resp.status_code == 500
    detail = resp.json().get("detail", "")
    assert "Traceback" not in detail
    assert 'File "' not in detail
    assert "internal path" not in detail
    assert "/etc/secrets" not in detail
    assert detail.startswith("internal error (ref: ")
