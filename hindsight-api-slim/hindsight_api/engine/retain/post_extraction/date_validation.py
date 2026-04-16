"""
Post-extraction date validation and correction.

Validates dates extracted by the LLM against the session date using
dateparser as an independent reference. Corrects common LLM errors:
- "last Friday" computed as 2 weeks ago instead of 1 week
- "last Wednesday" off by ±1 week
- Relative expressions resolved to wrong absolute dates

The key insight: the LLM does date arithmetic in its head during fact
extraction, and frequently gets it wrong by ±7 days. dateparser, as a
deterministic parser, provides a reliable second opinion.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Relative temporal expressions that dateparser can resolve.
# We only attempt correction for these patterns — absolute dates
# ("March 15, 2024") are left as-is since they don't involve computation.
_RELATIVE_PATTERNS = re.compile(
    r"(?i)\b("
    r"last\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"|last\s+(?:week|month|year)"
    r"|yesterday|the\s+day\s+before"
    r"|(?:a\s+)?(?:few|couple)\s+(?:days?|weeks?)\s+ago"
    r"|this\s+past\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"|the\s+(?:previous|prior)\s+(?:week|month|day)"
    r")\b"
)

# Pattern to find "(YYYY-MM-DD" or "YYYY-MM-DD)" or standalone ISO dates in fact text
_ISO_DATE_IN_TEXT = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

# When the relative expression is sourced from the chunk (not fact_text),
# attribution is not guaranteed — chunks often contain multiple unrelated
# temporal references. To avoid mis-correcting, we only accept chunk-sourced
# corrections whose diff matches the ±1 or ±2 week miscount pattern this
# feature was designed to catch (see module docstring). Other magnitudes
# almost always indicate the relative expression belongs to a different fact.
_CHUNK_PATH_PLAUSIBLE_DIFF_RANGES: tuple[tuple[int, int], ...] = (
    (6, 8),  # ±1 week miscount (most common)
    (13, 15),  # ±2 week miscount
)

# Maximum diff (days) for the fact-text path. The expression is definitely
# attributed to this fact, but extreme diffs (e.g., "last year" → 309d)
# indicate the expression is not a weekly miscount — the feature's designed
# scope. 21 days (3 weeks) is generous for any realistic weekly error.
_FACT_TEXT_MAX_DIFF_DAYS = 21


def _is_plausible_weekly_miscount(diff_days: int) -> bool:
    """Return True if diff matches the ±1/±2 week miscount pattern."""
    return any(lo <= diff_days <= hi for lo, hi in _CHUNK_PATH_PLAUSIBLE_DIFF_RANGES)


# Pattern to find "Month DD, YYYY" or "DD Month YYYY" in fact text
_READABLE_DATE_IN_TEXT = re.compile(
    r"\b("
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2}(?:,\s*|\s+)\d{4}"
    r"|"
    r"\d{1,2}\s+"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"(?:,?\s+\d{4})?"
    r")\b",
    re.IGNORECASE,
)


def _find_relative_expression(text: str) -> str | None:
    """Extract the first relative temporal expression from text."""
    m = _RELATIVE_PATTERNS.search(text)
    return m.group(0) if m else None


def _parse_date_with_dateparser(
    expression: str,
    reference_date: datetime,
) -> datetime | None:
    """Parse a relative date expression using dateparser.search_dates.

    Uses search_dates instead of dateparser.parse because parse() fails
    on "last Friday"/"last Monday" in dateparser 1.2.x, while search_dates
    handles them correctly.

    Uses PREFER_DATES_FROM='past' to match conversational context
    (people usually talk about things that already happened).
    """
    try:
        from dateparser.search import search_dates

        results = search_dates(
            expression,
            languages=["en"],
            settings={
                "RELATIVE_BASE": reference_date.replace(tzinfo=None),
                "PREFER_DATES_FROM": "past",
            },
        )
        if results:
            # Return the first date found
            _, parsed_date = results[0]
            return parsed_date.replace(tzinfo=timezone.utc)
    except Exception as e:
        logger.debug(f"dateparser failed for '{expression}': {e}")
    return None


def _replace_date_in_fact_text(
    text: str,
    old_date: datetime,
    new_date: datetime,
) -> str:
    """Replace occurrences of old_date with new_date in fact text.

    Handles both ISO format and readable format.
    """
    old_iso = old_date.strftime("%Y-%m-%d")
    new_iso = new_date.strftime("%Y-%m-%d")
    new_readable = new_date.strftime("%B %d, %Y").replace(" 0", " ")

    # Replace ISO dates
    text = text.replace(old_iso, new_iso)

    # Replace readable dates (e.g., "July 14, 2023" → "July 21, 2023")
    old_readables = [
        old_date.strftime("%B %d, %Y"),
        old_date.strftime("%B %d, %Y").replace(" 0", " "),
        old_date.strftime("%B %-d, %Y") if hasattr(old_date, "strftime") else "",
        old_date.strftime("%d %B %Y"),
        old_date.strftime("%d %B, %Y"),
    ]
    for old_r in old_readables:
        if old_r and old_r in text:
            text = text.replace(old_r, new_readable)
            break

    return text


def validate_and_correct_dates(
    facts: list,
    chunks: list,
    tolerance_days: int = 2,
) -> tuple[int, int]:
    """Validate and correct dates in extracted facts.

    For each fact with an occurred_start date and a relative temporal
    expression in its source chunk, uses dateparser to independently
    compute the date. If the LLM's date differs by more than
    ``tolerance_days``, replaces it with dateparser's result.

    Args:
        facts: List of ExtractedFact objects (mutated in-place).
        chunks: List of ChunkMetadata objects (for accessing source text).
        tolerance_days: Maximum acceptable difference between LLM and
            dateparser dates before correction is applied.

    Returns:
        Tuple of (checked_count, corrected_count).
    """
    # Build chunk lookup by chunk_index
    chunk_by_index = {c.chunk_index: c for c in chunks}

    checked = 0
    corrected = 0

    for fact in facts:
        if fact.occurred_start is None or fact.mentioned_at is None:
            continue

        # Find the source chunk text
        chunk = chunk_by_index.get(fact.chunk_index)
        chunk_text = chunk.chunk_text if chunk else ""

        # Look for relative temporal expression in fact_text first (high-confidence
        # path: the expression belongs to this fact). Fall back to chunk text only
        # when fact_text has none — this is lower confidence because chunks often
        # contain multiple temporal references belonging to different facts.
        relative_expr = _find_relative_expression(fact.fact_text)
        source = "fact" if relative_expr else None
        if not relative_expr and chunk_text:
            relative_expr = _find_relative_expression(chunk_text)
            if relative_expr:
                source = "chunk"

        if not relative_expr:
            continue

        checked += 1

        # Use dateparser with mentioned_at as reference
        computed_date = _parse_date_with_dateparser(relative_expr, fact.mentioned_at)
        if computed_date is None:
            continue

        # Compare with LLM's date
        diff_days = abs((computed_date - fact.occurred_start.replace(tzinfo=timezone.utc)).days)

        if diff_days > tolerance_days:
            # Chunk-path correction needs additional confidence check:
            # attribution is not guaranteed, so only accept diffs that match
            # the ±1/±2 week miscount pattern the feature was designed for.
            if source == "chunk" and not _is_plausible_weekly_miscount(diff_days):
                logger.debug(
                    "Skipping chunk-path date correction: diff=%dd outside "
                    "weekly miscount pattern (expr='%s', fact_date=%s, computed=%s)",
                    diff_days,
                    relative_expr,
                    fact.occurred_start.strftime("%Y-%m-%d"),
                    computed_date.strftime("%Y-%m-%d"),
                )
                continue

            # Fact-text path: attribution is certain but extreme diffs
            # (e.g., "last year" → 309d) are outside the weekly miscount
            # scope this feature targets. Cap at _FACT_TEXT_MAX_DIFF_DAYS.
            if source == "fact" and diff_days > _FACT_TEXT_MAX_DIFF_DAYS:
                logger.debug(
                    "Skipping fact-text date correction: diff=%dd exceeds "
                    "max %dd (expr='%s', fact_date=%s, computed=%s)",
                    diff_days,
                    _FACT_TEXT_MAX_DIFF_DAYS,
                    relative_expr,
                    fact.occurred_start.strftime("%Y-%m-%d"),
                    computed_date.strftime("%Y-%m-%d"),
                )
                continue

            old_date = fact.occurred_start
            new_date = computed_date

            logger.info(
                "Date corrected: %s → %s (expr='%s', ref=%s, diff=%dd)",
                old_date.strftime("%Y-%m-%d"),
                new_date.strftime("%Y-%m-%d"),
                relative_expr,
                fact.mentioned_at.strftime("%Y-%m-%d"),
                diff_days,
            )

            # Update structured dates
            fact.occurred_start = new_date
            if fact.occurred_end and fact.occurred_end == old_date:
                fact.occurred_end = new_date

            # Update date text in fact_text
            fact.fact_text = _replace_date_in_fact_text(fact.fact_text, old_date, new_date)

            corrected += 1

    return checked, corrected
