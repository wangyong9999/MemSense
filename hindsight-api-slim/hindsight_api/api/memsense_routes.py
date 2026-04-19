"""Single-entry dispatcher for MemSense fork-only HTTP routes.

Each fork-only endpoint lives in its own module and is registered here
behind its own feature flag, so upstream merges only ever touch one
line in ``http.py`` (the call to :func:`register_memsense_routes`).

Add new fork-only endpoints by importing their registration function
and wiring them to a flag below.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from ..config import get_config

logger = logging.getLogger(__name__)


def register_memsense_routes(app: FastAPI) -> None:
    """Register all flag-enabled MemSense fork-only routes."""
    cfg = get_config()

    if getattr(cfg, "erasure_api_enabled", False):
        from .erasure import register_erasure_route

        register_erasure_route(app)
        logger.info("MemSense: GDPR erase endpoint mounted at /v1/default/banks/{bank_id}/erase")
