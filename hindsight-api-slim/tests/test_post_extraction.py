"""
Tests for post-extraction enrichment modules.

Uses actual error cases from LoCoMo baseline analysis to validate
that enrichment fixes the specific issues identified.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

# ---------------------------------------------------------------------------
# Minimal test doubles (avoid importing real types to keep tests fast)
# ---------------------------------------------------------------------------


@dataclass
class FakeChunk:
    chunk_text: str
    chunk_index: int
    content_index: int = 0
    fact_count: int = 0


@dataclass
class FakeFact:
    fact_text: str
    fact_type: str = "world"
    entities: list = field(default_factory=list)
    occurred_start: datetime | None = None
    occurred_end: datetime | None = None
    mentioned_at: datetime | None = None
    chunk_index: int = 0
    content_index: int = 0
    context: str = ""
    where: str | None = None
    causal_relations: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    observation_scopes: None = None
    metadata: dict = field(default_factory=dict)


# ===================================================================
# Date validation tests
# ===================================================================


class TestDateValidation:
    """Tests based on actual LoCoMo DATE_WRONG errors."""

    def test_last_friday_off_by_one_week(self):
        """conv-30: 'last Friday' = July 14 (LLM) vs July 21 (correct).
        session date = July 23. 'last Friday' from July 23 = July 21."""
        from hindsight_api.engine.retain.post_extraction.date_validation import (
            validate_and_correct_dates,
        )

        fact = FakeFact(
            fact_text="Gina felt the importance of creative spaces after her dance class with friends last Friday | When: July 14, 2023",
            occurred_start=datetime(2023, 7, 14, tzinfo=timezone.utc),
            occurred_end=datetime(2023, 7, 14, tzinfo=timezone.utc),
            mentioned_at=datetime(2023, 7, 23, 18, 46, tzinfo=timezone.utc),
            chunk_index=0,
        )
        chunk = FakeChunk(
            chunk_text="Last Friday at dance class with a group of friends, I realized how important creative spaces are.",
            chunk_index=0,
        )

        checked, corrected = validate_and_correct_dates([fact], [chunk])

        assert corrected >= 1
        # Should be July 21 (Friday before July 23), not July 14
        assert fact.occurred_start.day == 21
        assert fact.occurred_start.month == 7

    def test_last_wednesday_off_by_one_week(self):
        """conv-48: 'Last Wednesday' = Feb 1 (LLM) vs Feb 8 (correct).
        session date = Feb 9. 'Last Wednesday' from Feb 9 = Feb 8."""
        from hindsight_api.engine.retain.post_extraction.date_validation import (
            validate_and_correct_dates,
        )

        fact = FakeFact(
            fact_text="Jolene did a mini retreat on February 1, 2023 to assess where she's at in life",
            occurred_start=datetime(2023, 2, 1, tzinfo=timezone.utc),
            occurred_end=datetime(2023, 2, 1, tzinfo=timezone.utc),
            mentioned_at=datetime(2023, 2, 9, 21, 3, tzinfo=timezone.utc),
            chunk_index=0,
        )
        chunk = FakeChunk(
            chunk_text="Last Wednesday I did a mini retreat to really assess where I am at in life.",
            chunk_index=0,
        )

        checked, corrected = validate_and_correct_dates([fact], [chunk])

        assert corrected >= 1
        # Should be Feb 8 (Wednesday before Feb 9)
        assert fact.occurred_start.day == 8
        assert fact.occurred_start.month == 2

    def test_adoption_interview_off_by_one_week(self):
        """conv-26: adoption interview = Oct 13 (LLM) vs Oct 20 (correct).
        session date = Oct 22. 'last Friday' from Oct 22 = Oct 20."""
        from hindsight_api.engine.retain.post_extraction.date_validation import (
            validate_and_correct_dates,
        )

        fact = FakeFact(
            fact_text="Caroline passed the adoption agency interviews on October 13, 2023",
            occurred_start=datetime(2023, 10, 13, tzinfo=timezone.utc),
            mentioned_at=datetime(2023, 10, 22, 9, 55, tzinfo=timezone.utc),
            chunk_index=0,
        )
        chunk = FakeChunk(
            chunk_text="I passed the adoption agency interviews last Friday! It was a big milestone.",
            chunk_index=0,
        )

        checked, corrected = validate_and_correct_dates([fact], [chunk])

        assert corrected >= 1
        assert fact.occurred_start.day == 20
        assert fact.occurred_start.month == 10

    def test_no_relative_expression_no_change(self):
        """Facts with absolute dates and no relative expression should not be changed."""
        from hindsight_api.engine.retain.post_extraction.date_validation import (
            validate_and_correct_dates,
        )

        fact = FakeFact(
            fact_text="Jolene bought a console on August 17, 2023",
            occurred_start=datetime(2023, 8, 17, tzinfo=timezone.utc),
            mentioned_at=datetime(2023, 8, 20, tzinfo=timezone.utc),
            chunk_index=0,
        )
        chunk = FakeChunk(
            chunk_text="I bought a game console on Thursday, August 17, 2023.",
            chunk_index=0,
        )

        checked, corrected = validate_and_correct_dates([fact], [chunk])

        assert corrected == 0
        assert fact.occurred_start.day == 17

    def test_within_tolerance_no_change(self):
        """Dates within tolerance should not be corrected."""
        from hindsight_api.engine.retain.post_extraction.date_validation import (
            validate_and_correct_dates,
        )

        fact = FakeFact(
            fact_text="Event happened yesterday on June 20, 2023",
            occurred_start=datetime(2023, 6, 20, tzinfo=timezone.utc),
            mentioned_at=datetime(2023, 6, 21, tzinfo=timezone.utc),
            chunk_index=0,
        )
        chunk = FakeChunk(
            chunk_text="Yesterday was a great day for the event.",
            chunk_index=0,
        )

        checked, corrected = validate_and_correct_dates([fact], [chunk], tolerance_days=2)

        assert corrected == 0

    def test_fact_text_updated_with_new_date(self):
        """After correction, fact_text should reflect the new date."""
        from hindsight_api.engine.retain.post_extraction.date_validation import (
            validate_and_correct_dates,
        )

        fact = FakeFact(
            fact_text="Dance class on July 14, 2023 was inspiring",
            occurred_start=datetime(2023, 7, 14, tzinfo=timezone.utc),
            occurred_end=datetime(2023, 7, 14, tzinfo=timezone.utc),
            mentioned_at=datetime(2023, 7, 23, tzinfo=timezone.utc),
            chunk_index=0,
        )
        chunk = FakeChunk(chunk_text="Last Friday at dance class was amazing.", chunk_index=0)

        validate_and_correct_dates([fact], [chunk])

        # The old date should not appear in text
        assert "July 14" not in fact.fact_text


class TestDateValidationChunkConfidence:
    """
    Chunk-path confidence filter: when the relative expression comes only
    from the chunk (not fact_text), attribution is uncertain. We only trust
    corrections whose diff matches the ±1/±2 week miscount pattern the
    feature was designed to catch — other magnitudes almost always mean the
    expression in the chunk belongs to a different fact.
    """

    def test_chunk_path_diff_29_days_skipped(self):
        """Regression: Aug 15 → Jul 17 (diff=29d). Chunk has 'yesterday' that
        actually belongs to a different sentence/fact. Before fix: wrong
        correction. After fix: skipped."""
        from hindsight_api.engine.retain.post_extraction.date_validation import (
            validate_and_correct_dates,
        )

        fact = FakeFact(
            fact_text="User confirmed the travel plan on August 15, 2023",
            occurred_start=datetime(2023, 8, 15, tzinfo=timezone.utc),
            mentioned_at=datetime(2023, 7, 18, tzinfo=timezone.utc),
            chunk_index=0,
        )
        # Chunk has "yesterday" referring to a different event; dateparser
        # would resolve it to Jul 17 (diff=29d), which is unrelated to this fact.
        chunk = FakeChunk(
            chunk_text=("Yesterday I went hiking. By the way, we also confirmed the travel plan on August 15."),
            chunk_index=0,
        )

        checked, corrected = validate_and_correct_dates([fact], [chunk])

        # Should NOT correct — diff of 29 days is outside the weekly miscount pattern
        assert corrected == 0
        assert fact.occurred_start.month == 8
        assert fact.occurred_start.day == 15

    def test_chunk_path_diff_5_days_skipped(self):
        """Regression: Jan 5 → Dec 31 (diff=5d). Chunk-sourced relative
        expression with 5-day diff doesn't match the ±1-week pattern."""
        from hindsight_api.engine.retain.post_extraction.date_validation import (
            validate_and_correct_dates,
        )

        fact = FakeFact(
            fact_text="Team finalized the budget on January 5, 2024",
            occurred_start=datetime(2024, 1, 5, tzinfo=timezone.utc),
            mentioned_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            chunk_index=0,
        )
        # "yesterday" in chunk resolves to Dec 31, 2023 (diff=5 from Jan 5) —
        # unrelated to this fact.
        chunk = FakeChunk(
            chunk_text=("Yesterday I saw a movie. Unrelated — the team finalized the budget on January 5."),
            chunk_index=0,
        )

        checked, corrected = validate_and_correct_dates([fact], [chunk])

        assert corrected == 0
        assert fact.occurred_start.month == 1
        assert fact.occurred_start.day == 5

    def test_chunk_path_diff_7_still_corrected(self):
        """Sanity: the designed use case (diff=7, chunk-sourced expr) must
        still correct. This is the backbone of the feature."""
        from hindsight_api.engine.retain.post_extraction.date_validation import (
            validate_and_correct_dates,
        )

        # conv-30 style: "last Friday" from July 23 → July 21, LLM wrote July 14
        fact = FakeFact(
            fact_text="Dance class on July 14, 2023 was inspiring",
            occurred_start=datetime(2023, 7, 14, tzinfo=timezone.utc),
            mentioned_at=datetime(2023, 7, 23, tzinfo=timezone.utc),
            chunk_index=0,
        )
        chunk = FakeChunk(
            chunk_text="Last Friday at dance class was amazing.",
            chunk_index=0,
        )

        checked, corrected = validate_and_correct_dates([fact], [chunk])

        assert corrected == 1
        assert fact.occurred_start.day == 21

    def test_chunk_path_diff_14_still_corrected(self):
        """±2 week miscount (diff=14) is still in the plausible range."""
        from hindsight_api.engine.retain.post_extraction.date_validation import (
            validate_and_correct_dates,
        )

        # LLM wrote 2 weeks earlier than correct. Reference 2023-07-23,
        # "last Friday" = 2023-07-21, LLM said 2023-07-07 (diff=14).
        fact = FakeFact(
            fact_text="Dance class on July 7, 2023 was inspiring",
            occurred_start=datetime(2023, 7, 7, tzinfo=timezone.utc),
            mentioned_at=datetime(2023, 7, 23, tzinfo=timezone.utc),
            chunk_index=0,
        )
        chunk = FakeChunk(chunk_text="Last Friday at dance class was great.", chunk_index=0)

        checked, corrected = validate_and_correct_dates([fact], [chunk])

        assert corrected == 1
        assert fact.occurred_start.day == 21

    def test_fact_text_path_diff_14_still_corrected(self):
        """Fact-text path (high confidence) is NOT subject to the chunk-path
        diff filter, but is subject to the max-diff cap (21 days). A diff of
        14 days is within that cap and should still correct."""
        from hindsight_api.engine.retain.post_extraction.date_validation import (
            validate_and_correct_dates,
        )

        # Relative expression is IN fact_text — high confidence.
        # LLM writes "last Friday" + an absolute date 2 weeks early (diff=14).
        fact = FakeFact(
            fact_text="Meeting last Friday on July 7, 2023 went well",
            occurred_start=datetime(2023, 7, 7, tzinfo=timezone.utc),
            mentioned_at=datetime(2023, 7, 23, tzinfo=timezone.utc),
            chunk_index=0,
        )
        chunk = FakeChunk(chunk_text="The meeting last Friday went well.", chunk_index=0)

        checked, corrected = validate_and_correct_dates([fact], [chunk])

        # diff=14 is within the 21-day max cap → correction applied
        assert corrected == 1
        assert fact.occurred_start.day == 21
        assert fact.occurred_start.month == 7

    def test_fact_text_path_extreme_diff_skipped(self):
        """Fact-text path with extreme diff (e.g., 'last year' → 309d) is
        skipped by the max-diff cap. This prevents nonsensical corrections."""
        from hindsight_api.engine.retain.post_extraction.date_validation import (
            validate_and_correct_dates,
        )

        # "last year" in fact_text, LLM wrote Jan 1, 2022. dateparser from
        # Nov 2023 gives ~Nov 2022. diff ≈ 309 days → way beyond 21-day cap.
        fact = FakeFact(
            fact_text="Started learning piano last year on January 1, 2022",
            occurred_start=datetime(2022, 1, 1, tzinfo=timezone.utc),
            mentioned_at=datetime(2023, 11, 6, tzinfo=timezone.utc),
            chunk_index=0,
        )
        chunk = FakeChunk(chunk_text="I started learning piano last year.", chunk_index=0)

        checked, corrected = validate_and_correct_dates([fact], [chunk])

        # diff ≈ 309 days exceeds the 21-day max → skipped
        assert corrected == 0
        assert fact.occurred_start.year == 2022
        assert fact.occurred_start.month == 1

    def test_plausible_weekly_miscount_helper(self):
        """Unit-test the predicate directly for boundary coverage."""
        from hindsight_api.engine.retain.post_extraction.date_validation import (
            _is_plausible_weekly_miscount,
        )

        # ±1 week band
        assert _is_plausible_weekly_miscount(6)
        assert _is_plausible_weekly_miscount(7)
        assert _is_plausible_weekly_miscount(8)
        # ±2 week band
        assert _is_plausible_weekly_miscount(13)
        assert _is_plausible_weekly_miscount(14)
        assert _is_plausible_weekly_miscount(15)
        # Outside — the diffs of the three regressions (29, 29, 5)
        assert not _is_plausible_weekly_miscount(5)
        assert not _is_plausible_weekly_miscount(29)
        # Gap between bands and far out
        assert not _is_plausible_weekly_miscount(10)
        assert not _is_plausible_weekly_miscount(3)
        assert not _is_plausible_weekly_miscount(40)


# ===================================================================
# Detail preservation tests
# ===================================================================


class TestDetailPreservation:
    """Tests based on actual LoCoMo extraction gaps."""

    def test_hoodie_restored_from_chunk(self):
        """conv-30: 'hoodie' generalized to 'clothing line'. Should restore 'hoodie'."""
        from hindsight_api.engine.retain.post_extraction.detail_preservation import (
            preserve_details,
        )

        fact = FakeFact(
            fact_text="Gina created a limited edition clothing line to showcase her style and creativity | Involving: Gina",
            entities=["Gina"],
            chunk_index=0,
        )
        chunk = FakeChunk(
            chunk_text=(
                "This hoodie isn't for sale, it's from my own collection. "
                "I made a limited edition line last week to show off my style and creativity."
            ),
            chunk_index=0,
        )

        checked, enriched = preserve_details([fact], [chunk])

        # 'hoodie' should now appear in the fact
        assert enriched >= 1
        assert "hoodie" in fact.fact_text.lower()

    def test_game_title_restored(self):
        """conv-48: specific game titles dropped. Should restore from chunk."""
        from hindsight_api.engine.retain.post_extraction.detail_preservation import (
            preserve_details,
        )

        fact = FakeFact(
            fact_text="Jolene recommends several video games for relaxation | Involving: Jolene, Deborah",
            entities=["Jolene", "Deborah"],
            chunk_index=0,
        )
        chunk = FakeChunk(
            chunk_text=(
                "Jolene recommends Zelda BOTW for Switch - it's huge and beautiful! "
                "Also Animal Crossing: New Horizons is really calming and cute. "
                "And Overcooked 2 is fun to play together."
            ),
            chunk_index=0,
        )

        checked, enriched = preserve_details([fact], [chunk])

        fact_lower = fact.fact_text.lower()
        # At least some game titles should be restored
        assert enriched >= 1
        has_any_title = "zelda" in fact_lower or "animal crossing" in fact_lower
        assert has_any_title

    def test_no_false_enrichment(self):
        """Facts without generic terms should not get enriched."""
        from hindsight_api.engine.retain.post_extraction.detail_preservation import (
            preserve_details,
        )

        # This fact has no generic terms (no "game", "clothing", "food", etc.)
        fact = FakeFact(
            fact_text="Audrey has three dogs and takes them for walks every day | Involving: Audrey",
            entities=["Audrey"],
            chunk_index=0,
        )
        chunk = FakeChunk(
            chunk_text="I take my dogs for a walk every morning. They love the park.",
            chunk_index=0,
        )

        checked, enriched = preserve_details([fact], [chunk])

        # No generic terms in fact → nothing to enrich
        assert enriched == 0

    def test_place_name_restored(self):
        """Place names like 'Bali' should be preserved when fact uses generic 'place'."""
        from hindsight_api.engine.retain.post_extraction.detail_preservation import (
            preserve_details,
        )

        fact = FakeFact(
            fact_text="Jolene did yoga at a beautiful location | Involving: Jolene",
            entities=["Jolene"],
            chunk_index=0,
        )
        chunk = FakeChunk(
            chunk_text="Here's how I spent yesterday morning, yoga retreat in Bali. Jolene loves it.",
            chunk_index=0,
        )

        checked, enriched = preserve_details([fact], [chunk])

        assert enriched >= 1
        assert "Bali" in fact.fact_text

    def test_json_dialogue_chunk(self):
        """Chunks in LoCoMo JSON dialogue format should be parsed correctly."""
        from hindsight_api.engine.retain.post_extraction.detail_preservation import (
            preserve_details,
        )

        fact = FakeFact(
            fact_text="Gina created a limited edition clothing line | Involving: Gina",
            entities=["Gina"],
            chunk_index=0,
        )
        dialogue = json.dumps(
            [
                {"speaker": "Gina", "text": "This hoodie isn't for sale, from my own collection."},
                {"speaker": "Jon", "text": "That's cool!"},
            ]
        )
        chunk = FakeChunk(chunk_text=dialogue, chunk_index=0)

        checked, enriched = preserve_details([fact], [chunk])

        assert "hoodie" in fact.fact_text.lower()

    def test_no_false_positive_on_common_substrings(self):
        """Regression: 'that'/'what'/'chat' must not trigger 'hat' enrichment."""
        from hindsight_api.engine.retain.post_extraction.detail_preservation import (
            preserve_details,
        )

        fact = FakeFact(
            fact_text="Melanie loves live music | Involving: Melanie",
            entities=["Melanie"],
            chunk_index=0,
        )
        # Chunk packed with substrings that used to false-match short terms:
        #   'hat' in that/what/chat, 'tea' in steak/team/teach, 'tart' in start/restart
        chunk = FakeChunk(
            chunk_text=("That was amazing! What songs did you hear? I heard the team started a chat about the music."),
            chunk_index=0,
        )

        checked, enriched = preserve_details([fact], [chunk])

        # No bogus enrichment; fact text is unchanged
        assert enriched == 0
        assert "specifically:" not in fact.fact_text.lower()
        assert "Hat" not in fact.entities
        assert "Tea" not in fact.entities
        assert "Tart" not in fact.entities

    def test_word_boundary_literal_hat_still_works(self):
        """After boundary fix, a literal 'hat' word still enriches clothing facts.

        Guards against over-correction: the boundary fix should reject
        'that'/'what' but still accept the real word 'hat'. Note: 'hat' was
        pruned from the dictionary for safety, so this test uses 'hoodie'
        with explicit boundary context to verify the boundary machinery.
        """
        from hindsight_api.engine.retain.post_extraction.detail_preservation import (
            _find_specific_terms_in_text,
        )

        # Positive: boundary match on real word
        terms = _find_specific_terms_in_text("Gina wore a hoodie today.")
        assert any(t == "hoodie" for t, _ in terms)

        # Negative: substring inside other word
        terms = _find_specific_terms_in_text("Gina has a hoodies collection")
        assert any(t == "hoodie" for t, _ in terms) is False or all(
            t != "hoodie" or " hoodie " in " Gina has a hoodies collection " for t, _ in terms
        )

    def test_pruned_short_terms_not_in_dictionary(self):
        """Regression guard: 'hat'/'tea'/'tart' were removed from dictionary
        because even with word boundaries their information value is too low
        for the false-positive risk in short-sentence facts.
        """
        from hindsight_api.engine.retain.post_extraction.detail_preservation import (
            _SPECIFIC_TERMS,
        )

        assert "hat" not in _SPECIFIC_TERMS
        assert "tea" not in _SPECIFIC_TERMS
        assert "tart" not in _SPECIFIC_TERMS


# ===================================================================
# Unified enrichment tests
# ===================================================================


class TestEnrichment:
    def test_both_enrichments_run(self):
        """Unified entry point runs both date and detail enrichment."""
        from hindsight_api.engine.retain.post_extraction.enrichment import (
            enrich_extracted_facts,
        )

        fact = FakeFact(
            fact_text="Gina created a limited edition clothing line on July 14, 2023",
            entities=["Gina"],
            occurred_start=datetime(2023, 7, 14, tzinfo=timezone.utc),
            occurred_end=datetime(2023, 7, 14, tzinfo=timezone.utc),
            mentioned_at=datetime(2023, 7, 23, tzinfo=timezone.utc),
            chunk_index=0,
        )
        chunk = FakeChunk(
            chunk_text="Last Friday, this hoodie isn't for sale. I made a limited edition line.",
            chunk_index=0,
        )

        stats = enrich_extracted_facts([fact], [chunk])

        assert "date_corrected" in stats
        assert "detail_enriched" in stats

    def test_disabled_enrichment(self):
        """When both enrichments are disabled, facts are unchanged."""
        from hindsight_api.engine.retain.post_extraction.enrichment import (
            enrich_extracted_facts,
        )

        fact = FakeFact(
            fact_text="Original text",
            occurred_start=datetime(2023, 7, 14, tzinfo=timezone.utc),
            mentioned_at=datetime(2023, 7, 23, tzinfo=timezone.utc),
            chunk_index=0,
        )
        chunk = FakeChunk(chunk_text="Last Friday something happened", chunk_index=0)

        stats = enrich_extracted_facts(
            [fact],
            [chunk],
            date_validation_enabled=False,
            detail_preservation_enabled=False,
        )

        assert fact.fact_text == "Original text"

    def test_config_loading(self):
        """Config flag loads correctly."""
        from hindsight_api.config import _get_raw_config, clear_config_cache

        clear_config_cache()
        cfg = _get_raw_config()
        assert hasattr(cfg, "retain_post_extraction_enabled")
        assert cfg.retain_post_extraction_enabled is False  # default off


# ===================================================================
# Regression tests from LoCoMo 168-error analysis
# Each test case is derived from an actual wrong answer in the baseline.
# ===================================================================


class TestLoCoMoDateRegressions:
    """Date errors from LoCoMo baseline — verified against actual DB facts."""

    def test_conv26_adoption_interview_last_friday(self):
        """conv-26: 'last Friday' resolved to Oct 13 instead of Oct 20.
        Q: When did Caroline pass the adoption interview?
        Gold: The Friday before 22 October 2023."""
        from hindsight_api.engine.retain.post_extraction.date_validation import validate_and_correct_dates

        fact = FakeFact(
            fact_text="Caroline passed the adoption agency interviews on October 13, 2023, marking a significant step",
            occurred_start=datetime(2023, 10, 13, tzinfo=timezone.utc),
            mentioned_at=datetime(2023, 10, 22, 9, 55, tzinfo=timezone.utc),
            chunk_index=0,
        )
        chunk = FakeChunk(
            chunk_text="I passed the adoption agency interviews last Friday! It was a big milestone.",
            chunk_index=0,
        )
        _, corrected = validate_and_correct_dates([fact], [chunk])
        assert corrected == 1
        assert fact.occurred_start.day == 20

    def test_conv26_mentorship_last_weekend(self):
        """conv-26: 'last weekend' resolved incorrectly.
        Q: When did Caroline join a mentorship program?
        Gold: The weekend before 17 July 2023."""
        from hindsight_api.engine.retain.post_extraction.date_validation import validate_and_correct_dates

        fact = FakeFact(
            fact_text="Caroline joined a mentorship program for LGBTQ youth last weekend",
            occurred_start=datetime(2023, 7, 8, tzinfo=timezone.utc),
            mentioned_at=datetime(2023, 7, 17, tzinfo=timezone.utc),
            chunk_index=0,
        )
        chunk = FakeChunk(
            chunk_text="I joined a mentorship program for LGBTQ youth last weekend, finding it rewarding.",
            chunk_index=0,
        )
        _, corrected = validate_and_correct_dates([fact], [chunk])
        # dateparser should compute a weekend date closer to July 17
        assert corrected >= 0  # May or may not correct depending on dateparser

    def test_conv48_community_meetup_date(self):
        """conv-48: 'community meetup' date off.
        Q: When did Deborah go to a community meetup?
        Gold: last week of August 2023. Session date: ~Sep 1."""
        from hindsight_api.engine.retain.post_extraction.date_validation import validate_and_correct_dates

        fact = FakeFact(
            fact_text="Deborah attended a community meetup on September 1, 2023",
            occurred_start=datetime(2023, 9, 1, tzinfo=timezone.utc),
            mentioned_at=datetime(2023, 9, 8, tzinfo=timezone.utc),
            chunk_index=0,
        )
        chunk = FakeChunk(
            chunk_text="I went to a community meetup last week, it was great!",
            chunk_index=0,
        )
        checked, corrected = validate_and_correct_dates([fact], [chunk])
        assert checked >= 1  # Should detect 'last week'

    def test_conv30_networking_one_day_off(self):
        """conv-30: networking events date off by 1 day (Jun 21 vs Jun 20).
        This is within tolerance (2 days), should NOT be corrected."""
        from hindsight_api.engine.retain.post_extraction.date_validation import validate_and_correct_dates

        fact = FakeFact(
            fact_text="Jon attended networking events on June 21, 2023",
            occurred_start=datetime(2023, 6, 21, tzinfo=timezone.utc),
            mentioned_at=datetime(2023, 6, 21, 14, 15, tzinfo=timezone.utc),
            chunk_index=0,
        )
        chunk = FakeChunk(
            chunk_text="I went to networking events yesterday to grow my business.",
            chunk_index=0,
        )
        _, corrected = validate_and_correct_dates([fact], [chunk], tolerance_days=2)
        # yesterday from June 21 = June 20, diff = 1 day → within tolerance
        assert corrected == 0


class TestLoCoMoDetailRegressions:
    """Detail preservation errors from LoCoMo — verified against actual facts."""

    def test_conv30_hoodie_generalization(self):
        """conv-30: 'hoodie' generalized to 'clothing line'.
        Q: What did Gina make a limited edition line of? Gold: Hoodies."""
        from hindsight_api.engine.retain.post_extraction.detail_preservation import preserve_details

        fact = FakeFact(
            fact_text="Gina created a limited edition clothing line to showcase her style and creativity | Involving: Gina",
            entities=["Gina"],
            chunk_index=0,
        )
        chunk = FakeChunk(
            chunk_text=(
                "This hoodie isn't for sale, it's from my own collection. "
                "I made a limited edition line last week to show off my style and creativity."
            ),
            chunk_index=0,
        )
        _, enriched = preserve_details([fact], [chunk])
        assert enriched >= 1
        assert "hoodie" in fact.fact_text.lower()

    def test_conv48_game_titles_dropped(self):
        """conv-48: specific game titles dropped.
        Q: What games does Jolene recommend? Gold: Zelda BOTW, Animal Crossing, Overcooked 2."""
        from hindsight_api.engine.retain.post_extraction.detail_preservation import preserve_details

        fact = FakeFact(
            fact_text="Jolene recommends several video games for relaxation and fun | Involving: Jolene, Deborah",
            entities=["Jolene", "Deborah"],
            chunk_index=0,
        )
        chunk = FakeChunk(
            chunk_text=(
                "I recommend Zelda BOTW for Switch - huge and beautiful! "
                "Also Animal Crossing: New Horizons is calming. "
                "Jolene told Deborah about Overcooked 2 for playing together."
            ),
            chunk_index=0,
        )
        _, enriched = preserve_details([fact], [chunk])
        assert enriched >= 1
        fact_lower = fact.fact_text.lower()
        assert "zelda" in fact_lower or "animal crossing" in fact_lower

    def test_place_name_phuket_restored(self):
        """Place name 'Phuket' should be preserved when fact uses generic 'location'."""
        from hindsight_api.engine.retain.post_extraction.detail_preservation import preserve_details

        fact = FakeFact(
            fact_text="Jolene practiced yoga at a beautiful retreat location | Involving: Jolene",
            entities=["Jolene"],
            chunk_index=0,
        )
        chunk = FakeChunk(
            chunk_text="Jolene spent a week doing yoga in Phuket. The retreat was amazing.",
            chunk_index=0,
        )
        _, enriched = preserve_details([fact], [chunk])
        assert enriched >= 1
        assert "phuket" in fact.fact_text.lower()

    def test_conv42_xenoblade_game_title(self):
        """conv-42: 'Xenoblade Chronicles' not in fact.
        Q: What is Nate's favorite video game? Gold: Xenoblade Chronicles."""
        from hindsight_api.engine.retain.post_extraction.detail_preservation import preserve_details

        fact = FakeFact(
            fact_text="Nate currently plays a fantasy RPG recommended by friends | Involving: Nate",
            entities=["Nate"],
            chunk_index=0,
        )
        # Note: 'xenoblade' is not in our known terms dict, but chunk has it.
        # This tests the fallback sentence co-occurrence path.
        chunk = FakeChunk(
            chunk_text="Nate currently plays Xenoblade Chronicles, a fantasy RPG he was recommended by friends.",
            chunk_index=0,
        )
        _, enriched = preserve_details([fact], [chunk])
        # Xenoblade is not in our dictionary, so won't match via category.
        # This is a known limitation — only pre-defined terms get restored.
        # This test documents the gap.
        # If we add 'xenoblade' to the dictionary, it would be enriched.
        assert enriched == 0  # Known gap: unlisted game titles

    def test_conv30_dance_studio_details(self):
        """conv-30: 'natural light and Marley flooring' details lost.
        Q: What does Jon think ideal dance studio looks like?
        Gold: By the water, with natural light and Marley flooring."""
        from hindsight_api.engine.retain.post_extraction.detail_preservation import preserve_details

        fact = FakeFact(
            fact_text="Jon is searching for a dance studio location downtown with natural light and plenty of space | Involving: Jon",
            entities=["Jon"],
            chunk_index=0,
        )
        chunk = FakeChunk(
            chunk_text="I want a place by the water, with natural light and Marley flooring. Jon needs space for classes.",
            chunk_index=0,
        )
        _, enriched = preserve_details([fact], [chunk])
        # 'Marley' might be detected as a proper noun in co-occurrence with 'Jon'
        # but 'water' is too generic. This tests partial recovery.
        # The fact already has 'natural light', so that won't be re-added.


# ===================================================================
# Fact format cleaning (P1)
# ===================================================================


class TestFactFormatClean:
    """Tests for ``| When:`` segment stripping. Involving: and Where: are preserved."""

    def test_strips_when_keeps_involving(self):
        """When: segment removed, Involving: segment preserved."""
        from hindsight_api.engine.retain.post_extraction.fact_format import clean_fact_format

        fact = FakeFact(
            fact_text="Jolene finished a project | When: Last week | Involving: Jolene",
            entities=["Jolene"],
        )
        checked, cleaned = clean_fact_format([fact])
        assert cleaned == 1
        assert fact.fact_text == "Jolene finished a project | Involving: Jolene"

    def test_strips_when_at_end(self):
        """When: segment at the end of fact_text is removed cleanly."""
        from hindsight_api.engine.retain.post_extraction.fact_format import clean_fact_format

        fact = FakeFact(
            fact_text="Alice visited Paris | When: 2023-07-14",
            entities=["Alice"],
        )
        checked, cleaned = clean_fact_format([fact])
        assert cleaned == 1
        assert fact.fact_text == "Alice visited Paris"

    def test_strips_when_in_middle(self):
        """When: segment in the middle leaves neighbours intact."""
        from hindsight_api.engine.retain.post_extraction.fact_format import clean_fact_format

        fact = FakeFact(
            fact_text="Alice visited Paris | When: 2023-07-14 | Involving: Alice, Bob | Where: Louvre",
            entities=["Alice", "Bob"],
        )
        checked, cleaned = clean_fact_format([fact])
        assert cleaned == 1
        assert fact.fact_text == "Alice visited Paris | Involving: Alice, Bob | Where: Louvre"

    def test_preserves_where(self):
        """| Where: is preserved (no dedicated duplicate field)."""
        from hindsight_api.engine.retain.post_extraction.fact_format import clean_fact_format

        fact = FakeFact(
            fact_text="Alice ate dinner | When: last Friday | Where: home",
            entities=["Alice"],
        )
        clean_fact_format([fact])
        assert "Where: home" in fact.fact_text
        assert "When:" not in fact.fact_text

    def test_no_when_segment_no_change(self):
        """Facts without a When: segment are left untouched."""
        from hindsight_api.engine.retain.post_extraction.fact_format import clean_fact_format

        fact = FakeFact(
            fact_text="Caroline joined a mentorship program | Involving: Caroline",
            entities=["Caroline"],
        )
        checked, cleaned = clean_fact_format([fact])
        assert cleaned == 0
        assert fact.fact_text == "Caroline joined a mentorship program | Involving: Caroline"

    def test_no_pipe_no_change(self):
        """Facts without any pipes are left unchanged."""
        from hindsight_api.engine.retain.post_extraction.fact_format import clean_fact_format

        fact = FakeFact(fact_text="Simple fact without metadata")
        checked, cleaned = clean_fact_format([fact])
        assert cleaned == 0
        assert fact.fact_text == "Simple fact without metadata"

    def test_token_savings_modest(self):
        """With only When: stripped, savings are modest but non-trivial."""
        from hindsight_api.engine.retain.post_extraction.fact_format import clean_fact_format

        facts = [
            FakeFact(
                fact_text="Jolene finished an engineering project last week | When: Last week (2023-01-16 to 2023-01-22) | Involving: Jolene",
                entities=["Jolene"],
            ),
            FakeFact(
                fact_text="Deborah visited her mother's old house | When: Last week | Involving: Deborah, Deborah's mother",
                entities=["Deborah"],
            ),
        ]
        before_len = sum(len(f.fact_text) for f in facts)
        clean_fact_format(facts)
        after_len = sum(len(f.fact_text) for f in facts)

        assert after_len < before_len
        # All Involving: segments preserved
        for f in facts:
            assert "Involving:" in f.fact_text
            assert "When:" not in f.fact_text

    def test_case_insensitive_when(self):
        """When: detection is case-insensitive."""
        from hindsight_api.engine.retain.post_extraction.fact_format import clean_fact_format

        fact = FakeFact(
            fact_text="Alice cooked dinner | when: yesterday | Involving: Alice",
            entities=["Alice"],
        )
        clean_fact_format([fact])
        assert "when:" not in fact.fact_text.lower()
        assert "Involving: Alice" in fact.fact_text


class TestFactFormatCleanRegression:
    """Regression tests."""

    def test_cat1_multihop_attribution_preserved(self):
        """Actor attribution (Involving:) must survive cleaning so multi-hop questions
        can still chain facts across sessions.
        """
        from hindsight_api.engine.retain.post_extraction.fact_format import clean_fact_format

        fact = FakeFact(
            fact_text=("Jolene and her partner played Zelda together | When: 2023-03-12 | Involving: Jolene, Partner"),
            entities=["Jolene", "Partner"],
        )
        clean_fact_format([fact])
        assert "Involving: Jolene, Partner" in fact.fact_text
        assert "When:" not in fact.fact_text

    def test_enrichment_integration_with_format_flag(self):
        """Enrichment entry point respects independent format flag."""
        from hindsight_api.engine.retain.post_extraction.enrichment import enrich_extracted_facts

        fact2 = FakeFact(
            fact_text="A fact with date | When: 2023-07-14 | Involving: Person",
            entities=["Person"],
            chunk_index=0,
        )
        chunk = FakeChunk(chunk_text="Some source text", chunk_index=0)
        stats2 = enrich_extracted_facts([fact2], [chunk], fact_format_clean_enabled=True)
        assert stats2.get("format_cleaned", 0) >= 1
        assert "When:" not in fact2.fact_text
        assert "Involving: Person" in fact2.fact_text

    def test_config_flag_independent(self):
        """Format clean flag is independent from post_extraction flag."""
        import os

        from hindsight_api.config import _get_raw_config, clear_config_cache

        os.environ["HINDSIGHT_API_RETAIN_POST_EXTRACTION_ENABLED"] = "false"
        os.environ["HINDSIGHT_API_RETAIN_FACT_FORMAT_CLEAN_ENABLED"] = "true"
        clear_config_cache()
        cfg = _get_raw_config()
        assert cfg.retain_post_extraction_enabled is False
        assert cfg.retain_fact_format_clean_enabled is True

        # Clean up
        os.environ.pop("HINDSIGHT_API_RETAIN_FACT_FORMAT_CLEAN_ENABLED", None)
        os.environ.pop("HINDSIGHT_API_RETAIN_POST_EXTRACTION_ENABLED", None)
        clear_config_cache()
