"""GDPR-style erase endpoint (MemSense-only).

Exposes ``POST /v1/default/banks/{bank_id}/erase`` which hard-deletes all
memory data for a bank while optionally preserving the bank shell so the
same ``bank_id`` can continue to be used after erasure. Emits a dedicated
``gdpr_erase`` audit entry so compliance teams get an unambiguous record
separate from routine ``delete_bank`` calls.

Opt-in behind ``HINDSIGHT_API_ERASURE_API_ENABLED`` (default off).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from ..engine.audit import AuditEntry
from ..extensions import AuthenticationError
from ..models import RequestContext

logger = logging.getLogger(__name__)


class ErasureResponse(BaseModel):
    """Summary of what was erased."""

    success: bool
    bank_id: str
    memory_units_deleted: int = Field(default=0)
    entities_deleted: int = Field(default=0)
    documents_deleted: int = Field(default=0)
    bank_dropped: bool = False


def _request_context(authorization: str | None = Header(default=None)) -> RequestContext:
    api_key: str | None = None
    if authorization:
        if authorization.lower().startswith("bearer "):
            api_key = authorization[7:].strip()
        else:
            api_key = authorization.strip()
    return RequestContext(api_key=api_key)


def register_erasure_route(app: FastAPI) -> None:
    """Register the GDPR erase endpoint on ``app``.

    Idempotent — safe to call once at app factory time.
    """

    @app.post(
        "/v1/default/banks/{bank_id}/erase",
        response_model=ErasureResponse,
        summary="GDPR-style erase of bank contents",
        description=(
            "Hard-deletes all memory units, entities, documents, and link data "
            "for the bank. By default the bank shell is preserved so the same "
            "bank_id can keep being used. Pass drop_bank=true to remove the "
            "bank record entirely. Emits a dedicated 'gdpr_erase' audit entry."
        ),
        operation_id="erase_bank",
        tags=["Compliance"],
    )
    async def erase_bank(
        bank_id: str,
        drop_bank: bool = Query(default=False, description="Also remove the bank record itself"),
        request_context: RequestContext = Depends(_request_context),
    ) -> ErasureResponse:
        memory = app.state.memory
        audit_logger = getattr(app.state, "audit_logger", None)

        try:
            result: dict[str, Any] = await memory.delete_bank(
                bank_id,
                delete_bank_profile=drop_bank,
                request_context=request_context,
            )
        except AuthenticationError:
            raise
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("erase_bank failed for %s: %s", bank_id, exc, exc_info=True)
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        response = ErasureResponse(
            success=True,
            bank_id=bank_id,
            memory_units_deleted=result.get("memory_units_deleted", 0),
            entities_deleted=result.get("entities_deleted", 0),
            documents_deleted=result.get("documents_deleted", 0),
            bank_dropped=drop_bank,
        )

        if audit_logger is not None:
            audit_logger.log_fire_and_forget(
                AuditEntry(
                    action="gdpr_erase",
                    transport="http",
                    bank_id=bank_id,
                    request={"drop_bank": drop_bank},
                    response=response.model_dump(),
                )
            )

        return response
