"""
Post-extraction fact text format cleaning.

Strips only the `| When: ...` segment from fact text. The `When:` value is
fully duplicated by the structured `occurred_start` / `occurred_end` fields
which are serialized alongside the fact text to the answer LLM, so removing
the inline pipe segment has zero information loss.

The `| Involving: ...` segment is KEPT because it is the only per-fact
actor attribution available to the answer LLM — the top-level `entities`
dict in the recall response is aggregated across all results and does not
preserve which entities belong to which fact.

`| Where: ...` is also kept because there is no dedicated location field
to duplicate it (would require a separate evaluation before removal).

Empirical basis:
  - MiniMax M2.7 conv-42/43 ablation: original all-strip was +3 on conv-43
    but also coincided with regressions elsewhere.
  - GLM-5 full 10-conv run (2026-04-17): original all-strip showed Cat1
    Multi-hop -1.42pp because per-fact `| Involving:` attribution was lost.
  - `occurred_start` is already in the JSON payload sent to the answer LLM
    (see `ScoredResult.to_dict` and `locomo_benchmark.generate_answer`),
    making `| When:` inline text strictly redundant.

Controlled by independent feature flag:
  HINDSIGHT_API_RETAIN_FACT_FORMAT_CLEAN_ENABLED (default: false)
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Match a ` | When: <content>` segment and its LEADING separator, leaving
# the trailing separator (and its preceding whitespace) to the next segment.
# Lazy match + lookahead ensures we stop at either the space-before-next-pipe
# or end-of-string, so middle segments don't collapse surrounding spaces.
#
# Example: "X | When: Y, Z | Involving: Q" → match " | When: Y, Z"
#                                            → result "X | Involving: Q"
_WHEN_SEGMENT_RE = re.compile(
    r"\s*\|\s*When:[^|]*?(?=\s+\||\s*$)",
    re.IGNORECASE,
)


def clean_fact_format(
    facts: list,
) -> tuple[int, int]:
    """Strip only the `| When:` segment from fact text.

    `| Involving:` and `| Where:` segments are preserved; see module
    docstring for the rationale.

    Args:
        facts: List of ExtractedFact objects (mutated in-place).

    Returns:
        Tuple of (checked_count, cleaned_count).
    """
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
