"""Redact PII patterns from extracted fact text.

Runs at the post-extraction stage (after LLM fact extraction, before
embedding generation) so stored memory and downstream retrieval never
contain raw PII. Opt-in behind ``HINDSIGHT_API_RETAIN_PII_REDACT_ENABLED``.

Matches are replaced with ``[REDACTED:<type>]``. Conservative by design —
credit-card numbers are Luhn-checked to cut false positives on arbitrary
16-digit strings.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Permissive phone pattern: optional +, country/area code groups, separators.
# Requires 10+ digits total to avoid matching short numeric sequences.
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}(?:[\s.-]?\d{2,4})?(?!\d)"
)

_SSN_RE = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")

# Candidate credit-card runs: 13–19 digits, possibly separated by spaces/dashes.
_CC_CANDIDATE_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")

_IPV4_RE = re.compile(r"(?<!\d)(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?!\d)")


def _luhn_ok(digits: str) -> bool:
    total = 0
    parity = len(digits) % 2
    for i, ch in enumerate(digits):
        d = ord(ch) - 48
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _redact_credit_cards(text: str) -> tuple[str, int]:
    count = 0

    def _sub(m: re.Match[str]) -> str:
        nonlocal count
        digits = re.sub(r"[ -]", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            count += 1
            return "[REDACTED:cc]"
        return m.group(0)

    return _CC_CANDIDATE_RE.sub(_sub, text), count


def _phone_digits_ok(match: str) -> bool:
    digits = re.sub(r"\D", "", match)
    return 10 <= len(digits) <= 15


def redact_pii(text: str) -> tuple[str, int]:
    """Redact PII in ``text``. Returns ``(new_text, redaction_count)``."""
    if not text:
        return text, 0

    total = 0

    # CC first so its digits are not re-matched by phone regex.
    text, n = _redact_credit_cards(text)
    total += n

    text, n = _SSN_RE.subn("[REDACTED:ssn]", text)
    total += n

    text, n = _EMAIL_RE.subn("[REDACTED:email]", text)
    total += n

    text, n = _IPV4_RE.subn("[REDACTED:ip]", text)
    total += n

    phone_count = 0

    def _phone_sub(m: re.Match[str]) -> str:
        nonlocal phone_count
        if _phone_digits_ok(m.group(0)):
            phone_count += 1
            return "[REDACTED:phone]"
        return m.group(0)

    text = _PHONE_RE.sub(_phone_sub, text)
    total += phone_count

    return text, total


def _entity_name(entity: object) -> str | None:
    """Extract a string name from either a plain ``str`` entity or an object
    with a ``.name`` attribute (pydantic Entity)."""
    if isinstance(entity, str):
        return entity
    name = getattr(entity, "name", None)
    return name if isinstance(name, str) else None


def _strip_pii_entities(entities: list) -> tuple[list, int]:
    """Remove entities whose name matches any PII pattern.

    Rather than replace the name with ``[REDACTED:...]`` — which would
    flow into entity resolution as a new phantom entity and pollute the
    graph — we DROP tainted entries outright. Returns the filtered list
    plus the number of entries dropped.
    """
    if not entities:
        return entities, 0

    clean: list = []
    dropped = 0
    for ent in entities:
        name = _entity_name(ent)
        if name is None:
            clean.append(ent)
            continue
        _, matches = redact_pii(name)
        if matches > 0:
            dropped += 1
            continue
        clean.append(ent)
    return clean, dropped


def redact_pii_in_facts(facts: list) -> tuple[int, int]:
    """Redact PII across ``fact_text``, ``where``, and ``entities`` of each
    fact in place.

    Entities matching a PII pattern are *dropped* rather than replaced with
    a ``[REDACTED:...]`` token — a redacted entity would be indexed and
    resolved as a new phantom. See FIX_PLAN_HARDENING.md §1, §8.

    Returns ``(facts_checked, facts_redacted)``.
    """
    checked = 0
    redacted_facts = 0

    for fact in facts:
        checked += 1
        fact_changed = False

        new_text, n = redact_pii(getattr(fact, "fact_text", "") or "")
        if n > 0:
            fact.fact_text = new_text
            fact_changed = True

        where = getattr(fact, "where", None)
        if where:
            new_where, n = redact_pii(where)
            if n > 0:
                fact.where = new_where
                fact_changed = True

        entities = getattr(fact, "entities", None)
        if entities:
            cleaned, dropped = _strip_pii_entities(entities)
            if dropped > 0:
                fact.entities = cleaned
                fact_changed = True

        if fact_changed:
            redacted_facts += 1

    if redacted_facts > 0:
        logger.debug("PII redaction: %d/%d facts had PII redacted", redacted_facts, checked)

    return checked, redacted_facts
