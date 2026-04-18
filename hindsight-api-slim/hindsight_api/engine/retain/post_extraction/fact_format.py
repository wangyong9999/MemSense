"""Strip the redundant ``| When:`` segment from fact text.

``| When:`` duplicates ``occurred_start`` / ``occurred_end`` in the
serialized response, so stripping it saves tokens without losing info.
``| Involving:`` and ``| Where:`` are preserved.

Flag: ``HINDSIGHT_API_RETAIN_FACT_FORMAT_CLEAN_ENABLED`` (default off).
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Match " | When: ..." eating its leading separator only.
# Lazy + lookahead so middle segments don't collapse spaces around the next pipe.
_WHEN_SEGMENT_RE = re.compile(
    r"\s*\|\s*When:[^|]*?(?=\s+\||\s*$)",
    re.IGNORECASE,
)


def clean_fact_format(
    facts: list,
) -> tuple[int, int]:
    """Strip ``| When:`` from each fact's text. Returns ``(checked, cleaned)``."""
    checked = 0
    cleaned = 0

    for fact in facts:
        if " | " not in fact.fact_text:
            continue

        checked += 1

        new_text = _WHEN_SEGMENT_RE.sub("", fact.fact_text).rstrip()

        if new_text == fact.fact_text.rstrip():
            continue

        if not new_text:
            continue

        fact.fact_text = new_text
        cleaned += 1

    if cleaned > 0:
        logger.debug("Fact format cleaned: %d/%d facts simplified (When: stripped)", cleaned, checked)

    return checked, cleaned
