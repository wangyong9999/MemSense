"""
Post-extraction enrichment for the retain pipeline.

MemSense enhancement: after LLM extracts facts from a chunk, this module
cross-checks and enriches the facts against the original source text to
fix common extraction issues:

1. detail_preservation: Restore proper nouns lost during concise extraction
2. date_validation: Correct date calculation errors using dateparser
3. signal_enrichment: Add BM25 keywords from source text (future)

All enrichments are independently toggleable and operate on ExtractedFact
objects before embedding generation, making them transparent to the rest
of the retain pipeline.
"""
