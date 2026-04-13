"""
Post-extraction fact text format cleaning.

Strips pipe-delimited metadata suffixes (| When: | Involving: | why)
from fact text, keeping only the core 'what' statement in natural language.

The stripped information is NOT lost — it is already stored in dedicated
fields:
  - occurred_start/end → dates
  - entities → who/people
  - text_signals → BM25 keywords

This reduces fact text token overhead by ~35-41%, improving the
signal-to-noise ratio when 100+ facts are sent to the answer LLM.

When the 'what' part lacks a subject (entity name), the primary entity
is appended in parentheses to maintain readability.

Controlled by independent feature flag:
  HINDSIGHT_API_RETAIN_FACT_FORMAT_CLEAN_ENABLED (default: false)
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Patterns for metadata segments after the first pipe
_PIPE_PREFIX_RE = re.compile(
    r"\s*\|\s*(?:When:|Involving:|Where:)",
    re.IGNORECASE,
)


def clean_fact_format(
    facts: list,
) -> tuple[int, int]:
    """Strip metadata suffixes from fact text, keep only 'what' part.

    If the 'what' part does not mention any of the fact's entities,
    appends the primary entity in parentheses to preserve the subject.

    Args:
        facts: List of ExtractedFact objects (mutated in-place).

    Returns:
        Tuple of (checked_count, cleaned_count).
    """
    checked = 0
    cleaned = 0

    for fact in facts:
        pipe_idx = fact.fact_text.find(" | ")
        if pipe_idx <= 0:
            continue

        checked += 1
        what_part = fact.fact_text[:pipe_idx].strip()

        if not what_part:
            continue

        # Check if 'what' part mentions any entity
        what_lower = what_part.lower()
        entities = fact.entities if hasattr(fact, "entities") and fact.entities else []
        entity_names = []
        for e in entities:
            if isinstance(e, str):
                entity_names.append(e)
            elif hasattr(e, "name"):
                entity_names.append(e.name)

        has_entity_in_what = any(name.lower() in what_lower for name in entity_names if len(name) >= 2)

        if has_entity_in_what or not entity_names:
            # What part already has the subject, or no entities to add
            fact.fact_text = what_part
        else:
            # Append primary entity so the fact isn't subjectless
            primary = entity_names[0]
            fact.fact_text = f"{what_part} ({primary})"

        cleaned += 1

    if cleaned > 0:
        logger.debug("Fact format cleaned: %d/%d facts simplified", cleaned, checked)

    return checked, cleaned
