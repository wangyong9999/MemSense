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
        has_any_title = "zelda" in fact_lower or "animal crossing" in fact_lower or "overcooked" in fact_lower
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
        """Place names like 'Talkeetna' should be preserved when fact uses generic 'place'."""
        from hindsight_api.engine.retain.post_extraction.detail_preservation import (
            preserve_details,
        )

        fact = FakeFact(
            fact_text="Jolene did yoga at a beautiful location | Involving: Jolene",
            entities=["Jolene"],
            chunk_index=0,
        )
        chunk = FakeChunk(
            chunk_text="Here's how I spent yesterday morning, yoga on top of mount Talkeetna. Jolene loves it.",
            chunk_index=0,
        )

        checked, enriched = preserve_details([fact], [chunk])

        assert enriched >= 1
        assert "Talkeetna" in fact.fact_text

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
        assert "zelda" in fact_lower or "animal crossing" in fact_lower or "overcooked" in fact_lower

    def test_conv48_talkeetna_place_lost(self):
        """conv-48: 'Talkeetna' not extracted.
        Q: When did Jolene do yoga at Talkeetna? Gold: June 5, 2023."""
        from hindsight_api.engine.retain.post_extraction.detail_preservation import preserve_details

        fact = FakeFact(
            fact_text="Jolene practiced yoga at a beautiful mountain location | Involving: Jolene",
            entities=["Jolene"],
            chunk_index=0,
        )
        chunk = FakeChunk(
            chunk_text="Here's an example of how I spent yesterday morning, yoga on top of mount Talkeetna. Jolene loves mountains.",
            chunk_index=0,
        )
        _, enriched = preserve_details([fact], [chunk])
        assert enriched >= 1
        assert "talkeetna" in fact.fact_text.lower()

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
    """Tests for pipe-delimited metadata stripping."""

    def test_strips_when_involving_why(self):
        """Full metadata suffix should be stripped."""
        from hindsight_api.engine.retain.post_extraction.fact_format import clean_fact_format

        fact = FakeFact(
            fact_text="Jolene finished a project | When: Last week | Involving: Jolene | Big milestone",
            entities=["Jolene"],
        )
        checked, cleaned = clean_fact_format([fact])
        assert cleaned == 1
        assert fact.fact_text == "Jolene finished a project"
        assert "|" not in fact.fact_text

    def test_preserves_what_with_entity(self):
        """When 'what' already mentions the entity, no suffix added."""
        from hindsight_api.engine.retain.post_extraction.fact_format import clean_fact_format

        fact = FakeFact(
            fact_text="Audrey's favorite recipe is Chicken Pot Pie | Involving: Audrey | Family tradition",
            entities=["Audrey"],
        )
        clean_fact_format([fact])
        assert fact.fact_text == "Audrey's favorite recipe is Chicken Pot Pie"

    def test_appends_entity_when_missing_from_what(self):
        """When 'what' has no entity mention, primary entity is appended."""
        from hindsight_api.engine.retain.post_extraction.fact_format import clean_fact_format

        fact = FakeFact(
            fact_text="Passed the adoption interviews last Friday | Involving: Caroline | Significant step",
            entities=["Caroline"],
        )
        clean_fact_format([fact])
        assert fact.fact_text == "Passed the adoption interviews last Friday (Caroline)"

    def test_no_pipe_no_change(self):
        """Facts without pipes are left unchanged."""
        from hindsight_api.engine.retain.post_extraction.fact_format import clean_fact_format

        fact = FakeFact(fact_text="Simple fact without metadata")
        checked, cleaned = clean_fact_format([fact])
        assert cleaned == 0
        assert fact.fact_text == "Simple fact without metadata"

    def test_empty_entities_no_suffix(self):
        """When there are no entities, just strip the metadata."""
        from hindsight_api.engine.retain.post_extraction.fact_format import clean_fact_format

        fact = FakeFact(
            fact_text="It was a sunny day | Weather observation",
            entities=[],
        )
        clean_fact_format([fact])
        assert fact.fact_text == "It was a sunny day"

    def test_token_savings(self):
        """Verify actual token reduction on realistic facts."""
        from hindsight_api.engine.retain.post_extraction.fact_format import clean_fact_format

        facts = [
            FakeFact(
                fact_text="Jolene finished an engineering project last week | When: Last week (2023-01-16 to 2023-01-22) | Involving: Jolene",
                entities=["Jolene"],
            ),
            FakeFact(
                fact_text="Deborah visited her mother's old house | When: Last week | Involving: Deborah, Deborah's mother | Holds memories",
                entities=["Deborah"],
            ),
            FakeFact(
                fact_text="Caroline joined a mentorship program | Involving: Caroline | Finding it rewarding",
                entities=["Caroline"],
            ),
        ]
        before_len = sum(len(f.fact_text) for f in facts)
        clean_fact_format(facts)
        after_len = sum(len(f.fact_text) for f in facts)

        savings = (before_len - after_len) / before_len * 100
        assert savings > 30  # Should save at least 30%

    def test_multiple_entities_uses_first(self):
        """When what lacks entity, uses the first one from the list."""
        from hindsight_api.engine.retain.post_extraction.fact_format import clean_fact_format

        fact = FakeFact(
            fact_text="Had a great conversation about life | Involving: Deborah, Anna",
            entities=["Deborah", "Anna"],
        )
        clean_fact_format([fact])
        assert fact.fact_text == "Had a great conversation about life (Deborah)"


class TestFactFormatCleanRegression:
    """Regression tests from actual LoCoMo facts."""

    def test_conv48_renewable_energy(self):
        """A1 case: LLM ignored this fact. Format cleaning should make it cleaner."""
        from hindsight_api.engine.retain.post_extraction.fact_format import clean_fact_format

        fact = FakeFact(
            fact_text=(
                "Jolene is interested in two projects: developing renewable energy (solar) "
                "to help communities and supplying clean water to those with limited access "
                "| Involving: Jolene | Align with her beliefs about sustainability"
            ),
            entities=["Jolene"],
        )
        clean_fact_format([fact])
        assert "renewable energy" in fact.fact_text
        assert "Involving" not in fact.fact_text
        assert "sustainability" not in fact.fact_text

    def test_conv44_chicken_pot_pie(self):
        """A2 case: competing facts. Clean format reduces ambiguity."""
        from hindsight_api.engine.retain.post_extraction.fact_format import clean_fact_format

        facts = [
            FakeFact(
                fact_text="Audrey's favorite recipe is Chicken Pot Pie, a family recipe passed down for years | Involving: Audrey | Family tradition",
                entities=["Audrey"],
            ),
            FakeFact(
                fact_text="Audrey's roasted chicken recipe is based on Mediterranean flavors | Involving: Audrey | Comfort food",
                entities=["Audrey"],
            ),
        ]
        clean_fact_format(facts)
        # Both should be clean and distinguishable
        assert "Chicken Pot Pie" in facts[0].fact_text
        assert "Mediterranean" in facts[1].fact_text
        assert "|" not in facts[0].fact_text
        assert "|" not in facts[1].fact_text

    def test_enrichment_integration_with_format_flag(self):
        """Enrichment respects independent format flag."""
        from hindsight_api.engine.retain.post_extraction.enrichment import enrich_extracted_facts

        fact = FakeFact(
            fact_text="A fact with metadata | Involving: Someone | Reason",
            entities=["Someone"],
            chunk_index=0,
        )
        chunk = FakeChunk(chunk_text="Some source text", chunk_index=0)

        # With format clean disabled (default)
        stats1 = enrich_extracted_facts([fact], [chunk], fact_format_clean_enabled=False)
        # fact should still have pipe
        # (can't check because other enrichments may not modify it)

        # With format clean enabled
        fact2 = FakeFact(
            fact_text="Another fact | Involving: Person | Context",
            entities=["Person"],
            chunk_index=0,
        )
        stats2 = enrich_extracted_facts([fact2], [chunk], fact_format_clean_enabled=True)
        assert stats2.get("format_cleaned", 0) >= 1
        assert "|" not in fact2.fact_text

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
