"""Tenant-wide usage reporting endpoint (MemSense-only).

Aggregates the ``token_usage`` table across arbitrary date ranges and a
chosen grouping axis — operation, bank, or day — so operators have the
data needed for billing, cost trends, and customer-facing invoices.

Complements the upstream per-bank endpoint
``/v1/default/banks/{bank_id}/token-usage`` (which is fixed to a
rolling N-day window and a single bank).

Opt-in behind ``HINDSIGHT_API_USAGE_API_ENABLED`` (default off).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from ..extensions import AuthenticationError
from ..models import RequestContext

logger = logging.getLogger(__name__)

GroupBy = Literal["operation", "bank", "day"]


class UsageGroup(BaseModel):
    group: str = Field(description="The group key value (operation name, bank_id, or ISO date).")
    operation_count: int = 0
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    context_tokens: int = 0
    saved_tokens: int = 0


class UsageResponse(BaseModel):
    bank_id: str | None = None
    start: datetime
    end: datetime
    group_by: GroupBy
    total_operations: int
    totals: UsageGroup
    groups: list[UsageGroup]


_GROUP_EXPR = {
    "operation": "operation",
    "bank": "bank_id",
    "day": "to_char(date_trunc('day', created_at), 'YYYY-MM-DD')",
}


def _request_context(authorization: str | None = Header(default=None)) -> RequestContext:
    api_key: str | None = None
    if authorization:
        if authorization.lower().startswith("bearer "):
            api_key = authorization[7:].strip()
        else:
            api_key = authorization.strip()
    return RequestContext(api_key=api_key)


def _default_window() -> tuple[datetime, datetime]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    return start, end


def register_usage_route(app: FastAPI) -> None:
    """Register the tenant-wide usage endpoint on ``app``."""

    @app.get(
        "/v1/default/usage",
        response_model=UsageResponse,
        summary="Tenant-wide token usage report",
        description=(
            "Aggregates token_usage rows over an arbitrary time window, grouped by "
            "operation, bank, or day. Omit bank_id to report across all banks."
        ),
        operation_id="get_tenant_usage",
        tags=["Usage"],
    )
    async def get_tenant_usage(
        bank_id: str | None = Query(default=None, description="Filter to a single bank"),
        start: datetime | None = Query(default=None, description="Window start (inclusive, ISO 8601)"),
        end: datetime | None = Query(default=None, description="Window end (exclusive, ISO 8601)"),
        group_by: GroupBy = Query(default="operation"),
        request_context: RequestContext = Depends(_request_context),
    ) -> UsageResponse:
        if start is None or end is None:
            default_start, default_end = _default_window()
            start = start or default_start
            end = end or default_end
        if start >= end:
            raise HTTPException(status_code=400, detail="start must be strictly before end")

        group_expr = _GROUP_EXPR[group_by]
        try:
            pool = await app.state.memory._get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    f"""
                    SELECT
                        {group_expr} AS group_key,
                        COUNT(*) AS operation_count,
                        COALESCE(SUM(llm_input_tokens), 0) AS llm_input_tokens,
                        COALESCE(SUM(llm_output_tokens), 0) AS llm_output_tokens,
                        COALESCE(SUM(context_tokens), 0) AS context_tokens,
                        COALESCE(SUM(saved_tokens), 0) AS saved_tokens
                    FROM token_usage
                    WHERE created_at >= $1
                      AND created_at < $2
                      AND ($3::text IS NULL OR bank_id = $3)
                    GROUP BY group_key
                    ORDER BY group_key
                    """,
                    start,
                    end,
                    bank_id,
                )
        except (AuthenticationError, HTTPException):
            raise
        except Exception as exc:
            logger.error("usage query failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        groups = [
            UsageGroup(
                group=str(row["group_key"]) if row["group_key"] is not None else "",
                operation_count=int(row["operation_count"]),
                llm_input_tokens=int(row["llm_input_tokens"]),
                llm_output_tokens=int(row["llm_output_tokens"]),
                context_tokens=int(row["context_tokens"]),
                saved_tokens=int(row["saved_tokens"]),
            )
            for row in rows
        ]

        totals = UsageGroup(
            group="__total__",
            operation_count=sum(g.operation_count for g in groups),
            llm_input_tokens=sum(g.llm_input_tokens for g in groups),
            llm_output_tokens=sum(g.llm_output_tokens for g in groups),
            context_tokens=sum(g.context_tokens for g in groups),
            saved_tokens=sum(g.saved_tokens for g in groups),
        )

        return UsageResponse(
            bank_id=bank_id,
            start=start,
            end=end,
            group_by=group_by,
            total_operations=totals.operation_count,
            totals=totals,
            groups=groups,
        )
