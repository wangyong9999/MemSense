"""
Unified entry point for post-extraction enrichment.

Orchestrates all enrichment steps in sequence. Each step is independent,
toggleable, and operates on ExtractedFact objects in-place.

Called from orchestrator._extract_and_embed() after fact extraction
and before embedding generation.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


def enrich_extracted_facts(
    facts: list,
    chunks: list,
    *,
    date_validation_enabled: bool = True,
    detail_preservation_enabled: bool = True,
    date_tolerance_days: int = 2,
) -> dict:
    """Run all post-extraction enrichment steps.

    Args:
        facts: List of ExtractedFact objects (mutated in-place).
        chunks: List of ChunkMetadata objects (source text for cross-checking).
        date_validation_enabled: Whether to validate/correct dates.
        detail_preservation_enabled: Whether to restore lost proper nouns.
        date_tolerance_days: Max days difference before date is corrected.

    Returns:
        Stats dict with counts from each enrichment step.
    """
    stats: dict[str, int | float] = {}
    start = time.time()

    if date_validation_enabled and facts and chunks:
        from .date_validation import validate_and_correct_dates

        step_start = time.time()
        checked, corrected = validate_and_correct_dates(facts, chunks, tolerance_days=date_tolerance_days)
        stats["date_checked"] = checked
        stats["date_corrected"] = corrected
        stats["date_time"] = round(time.time() - step_start, 3)

    if detail_preservation_enabled and facts and chunks:
        from .detail_preservation import preserve_details

        step_start = time.time()
        checked, enriched = preserve_details(facts, chunks)
        stats["detail_checked"] = checked
        stats["detail_enriched"] = enriched
        stats["detail_time"] = round(time.time() - step_start, 3)

    stats["total_time"] = round(time.time() - start, 3)

    if stats.get("date_corrected", 0) > 0 or stats.get("detail_enriched", 0) > 0:
        logger.info(
            "Post-extraction enrichment: %s",
            ", ".join(f"{k}={v}" for k, v in stats.items()),
        )

    return stats
