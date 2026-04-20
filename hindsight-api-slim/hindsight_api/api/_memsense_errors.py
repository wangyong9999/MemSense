"""Shared error-handling helpers for MemSense fork-only endpoints.

Prevents 5xx responses from echoing exception messages (which may contain
file paths, query fragments, or internal identifiers). Full detail is
logged server-side with a request id; the caller receives only the id
so operators can correlate a report to the log line.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import HTTPException

logger = logging.getLogger(__name__)


def raise_opaque_500(log_prefix: str, exc: BaseException) -> None:
    """Log ``exc`` under ``log_prefix`` with a fresh request id and raise a
    sanitized HTTP 500 whose detail only mentions the id.

    Callers typically want ``raise raise_opaque_500(...)`` — but since this
    helper raises, the return type is ``NoReturn`` in practice. Using
    ``raise from exc`` preserves the cause chain in logs.
    """
    ref = uuid.uuid4().hex[:12]
    logger.error("%s failed [ref=%s]: %s", log_prefix, ref, exc, exc_info=True)
    raise HTTPException(status_code=500, detail=f"internal error (ref: {ref})") from exc
