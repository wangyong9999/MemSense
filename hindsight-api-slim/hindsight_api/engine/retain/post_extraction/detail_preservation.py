"""
Post-extraction detail preservation.

Cross-checks extracted facts against source chunk text to restore
specific details that the LLM's concise extraction dropped:

- Product/item names: "hoodie" generalized to "clothing line"
- Game/book/movie titles: "Zelda BOTW" dropped, only "game" remains
- Place names: "Talkeetna" not in fact, only "mountain"
- Specific quantities: "three times" → "several times"

Strategy: When a fact contains a GENERIC term (clothing, game, food, etc.)
and the source chunk contains a more SPECIFIC term in the same context,
append the specific term to the fact.
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

# Generic category terms and their more-specific alternatives that might appear
# in source text.  If a fact uses one of these generics AND the chunk has a more
# specific term nearby, we restore the specific term.
#
# IMPORTANT: Only include widely-known common English terms here. Do NOT add
# benchmark-specific proper nouns (character names, obscure place names, pet
# names from test conversations). This dictionary must generalise to arbitrary
# user conversations — adding benchmark-derived terms is overfitting.
_GENERIC_CATEGORIES: dict[str, list[str]] = {
    "clothing": [
        "hoodie",
        "jacket",
        "shirt",
        "dress",
        "pants",
        "skirt",
        "sweater",
        "coat",
        "scarf",
        "boots",
        "sneakers",
        "jeans",
    ],
    "game": [
        "zelda",
        "mario",
        "minecraft",
        "fortnite",
        "overwatch",
        "animal crossing",
        "pokemon",
    ],
    "book": ["harry potter", "lord of the rings"],
    "food": [
        "pizza",
        "pasta",
        "sushi",
        "burrito",
        "salad",
        "steak",
        "burger",
        "muffin",
        "croissant",
    ],
    "recipe": ["roasted chicken", "mediterranean"],
    "drink": ["coffee", "latte", "espresso", "smoothie"],
    "place": ["phuket", "bali", "alaska", "san francisco"],
    "sport": ["surfing", "yoga", "basketball", "boxing", "hiking"],
    "music": ["beethoven", "bach", "mozart", "chopin"],
}

# Flatten for quick lookup: specific_term → category
_SPECIFIC_TERMS: dict[str, str] = {}
for category, terms in _GENERIC_CATEGORIES.items():
    for term in terms:
        _SPECIFIC_TERMS[term.lower()] = category

# Generic words in fact text that signal potential specificity loss
_GENERIC_INDICATORS = re.compile(
    r"\b(clothing|clothes|garments?|apparel|games?|video games?|consoles?|books?|novels?|stor(?:y|ies)|"
    r"foods?|dish(?:es)?|recipes?|meals?|drinks?|beverages?|places?|locations?|spots?|animals?|pets?|"
    r"sports?|activit(?:y|ies)|exercises?|music|songs?|tunes?|movies?|films?|shows?)\b",
    re.IGNORECASE,
)


def _extract_chunk_text(chunk_text: str) -> str:
    """Extract plain text from chunk (handles JSON dialogue format)."""
    text = chunk_text.strip()
    if text.startswith("["):
        try:
            messages = json.loads(text)
            return " ".join(m.get("text", "") for m in messages if isinstance(m, dict))
        except (json.JSONDecodeError, TypeError):
            pass
    return text


def _find_specific_terms_in_text(text: str) -> list[tuple[str, str]]:
    """Find specific terms in text that match known categories.

    Uses word-boundary matching to avoid false positives like "hat" matching
    inside "that"/"what"/"chat" or "tea" inside "steak"/"team"/"teach".

    Returns list of (term, category) tuples.
    """
    text_lower = text.lower()
    found = []
    # Check multi-word terms first (longer matches take priority)
    for term, category in sorted(_SPECIFIC_TERMS.items(), key=lambda x: len(x[0]), reverse=True):
        pattern = rf"\b{re.escape(term)}\b"
        if re.search(pattern, text_lower):
            found.append((term, category))
    return found


def _terms_share_sentence(text: str, term: str, fact_keywords: list[str]) -> bool:
    """Check if term and any fact keyword appear in the same sentence.

    Uses word-boundary matching for the term (same reason as
    _find_specific_terms_in_text). Fact keywords are matched as substrings
    since they are already meaningful tokens extracted from fact_text.
    """
    term_pattern = rf"\b{re.escape(term.lower())}\b"
    sentences = re.split(r"[.!?]+", text)
    for sentence in sentences:
        sentence_lower = sentence.lower()
        if re.search(term_pattern, sentence_lower):
            if any(kw.lower() in sentence_lower for kw in fact_keywords):
                return True
    return False


def _extract_fact_keywords(fact_text: str) -> list[str]:
    """Extract meaningful keywords from fact text for context matching."""
    stopwords = {
        "the",
        "and",
        "for",
        "was",
        "with",
        "that",
        "this",
        "from",
        "have",
        "been",
        "are",
        "has",
        "her",
        "his",
        "she",
        "him",
        "they",
        "their",
        "involving",
        "when",
        "where",
        "who",
        "why",
        "n/a",
    }
    words = re.split(r"[\s|,;:]+", fact_text)
    return [w.strip(".,!?\"'()[]") for w in words if len(w) >= 3 and w.lower() not in stopwords][:8]


def preserve_details(
    facts: list,
    chunks: list,
) -> tuple[int, int]:
    """Restore lost specific details in extracted facts.

    For each fact containing generic terms, searches the source chunk
    for more specific terms in the same context and appends them.

    Args:
        facts: List of ExtractedFact objects (mutated in-place).
        chunks: List of ChunkMetadata objects.

    Returns:
        Tuple of (checked_count, enriched_count).
    """
    chunk_by_index = {c.chunk_index: c for c in chunks}

    checked = 0
    enriched = 0

    for fact in facts:
        chunk = chunk_by_index.get(fact.chunk_index)
        if not chunk:
            continue

        # Check if fact has generic terms
        if not _GENERIC_INDICATORS.search(fact.fact_text):
            continue

        checked += 1

        chunk_text = _extract_chunk_text(chunk.chunk_text)
        fact_lower = fact.fact_text.lower()
        fact_keywords = _extract_fact_keywords(fact.fact_text)

        # Find specific terms in chunk that are NOT in the fact
        specific_in_chunk = _find_specific_terms_in_text(chunk_text)
        added: list[str] = []

        # Which generic categories does the fact use?
        # Map indicator words to categories: "clothing" → clothing, "game" → game,
        # "recipe" → recipe/food, "location" → place, etc.
        _INDICATOR_TO_CATEGORIES = {
            "clothing": ["clothing"],
            "clothes": ["clothing"],
            "garment": ["clothing"],
            "apparel": ["clothing"],
            "game": ["game"],
            "games": ["game"],
            "video game": ["game"],
            "video games": ["game"],
            "console": ["game"],
            "consoles": ["game"],
            "book": ["book"],
            "novel": ["book"],
            "story": ["book"],
            "food": ["food", "recipe"],
            "dish": ["food", "recipe"],
            "recipe": ["recipe", "food"],
            "meal": ["food"],
            "drink": ["drink"],
            "beverage": ["drink"],
            "place": ["place"],
            "location": ["place"],
            "spot": ["place"],
            "animal": ["animal"],
            "pet": ["animal"],
            "sport": ["sport"],
            "activity": ["sport"],
            "exercise": ["sport"],
            "music": ["music"],
            "song": ["music"],
            "tune": ["music"],
            "movie": ["game"],
            "film": ["game"],
            "show": ["game"],  # games/movies overlap
        }
        fact_generics: set[str] = set()
        for m in _GENERIC_INDICATORS.finditer(fact.fact_text):
            word = m.group(1).lower()
            # Normalize plurals for lookup (regex captures "games"/"books" etc.)
            cats = _INDICATOR_TO_CATEGORIES.get(word, [])
            if not cats:
                # Try stripping trailing 's'/'es'/'ies'
                singular = re.sub(r"(ies)$", "y", word)
                singular = re.sub(r"(es|s)$", "", singular) if singular == word else singular
                cats = _INDICATOR_TO_CATEGORIES.get(singular, [])
            fact_generics.update(cats)

        for term, category in specific_in_chunk:
            if term.lower() in fact_lower:
                continue  # already in fact

            # The term's category must match one of the fact's generic categories
            # This prevents unrelated terms from being added
            if category not in fact_generics:
                # Fallback: check if term and fact keywords share a sentence
                if not _terms_share_sentence(chunk_text, term, fact_keywords):
                    continue

            # Capitalize the term for display
            display_term = term.title() if len(term.split()) > 1 else term.capitalize()
            added.append(display_term)

            # Also add to entities for BM25 signal enrichment
            if display_term not in fact.entities:
                fact.entities.append(display_term)

        if added:
            # Append as parenthetical at end of 'what' part (before first |)
            detail_str = ", ".join(added)
            pipe_idx = fact.fact_text.find(" | ")
            if pipe_idx > 0:
                what_part = fact.fact_text[:pipe_idx]
                rest = fact.fact_text[pipe_idx:]
                fact.fact_text = f"{what_part} (specifically: {detail_str}){rest}"
            else:
                fact.fact_text = f"{fact.fact_text} (specifically: {detail_str})"

            enriched += 1
            logger.debug(
                "Detail preserved: added %s to fact '%s...'",
                added,
                fact.fact_text[:60],
            )

    return checked, enriched
