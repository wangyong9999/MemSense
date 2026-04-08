"""Add L0/L1 summary fields and importance scoring to memory_units

Revision ID: m9h0i1j2k3l4
Revises: l8g9h0i1j2k3
Create Date: 2026-04-08

Adds columns for Precision-per-Token output tier selection:
- l0_digest: Short text summary (~80 tokens) for lightweight recall
- l1_structured: Structured 5W summary (~300 tokens) for Tier-A output
- importance_score: Importance weight for density-aware budget fill
- maturity: Lifecycle tier (draft/validated/core/stale)

All columns are nullable/have defaults, so existing INSERT statements
continue to work without modification until L0/L1 generation is enabled.
"""

from collections.abc import Sequence

from alembic import context, op

# revision identifiers, used by Alembic.
revision: str = "m9h0i1j2k3l4"
down_revision: str | Sequence[str] | None = "l8g9h0i1j2k3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _get_schema_prefix() -> str:
    """Get schema prefix for table names (required for multi-tenant support)."""
    schema = context.config.get_main_option("target_schema")
    return f'"{schema}".' if schema else ""


def upgrade() -> None:
    schema = _get_schema_prefix()

    # L0 digest: short summary for fast scanning (~80 tokens)
    op.execute(f"""
        ALTER TABLE {schema}memory_units
        ADD COLUMN IF NOT EXISTS l0_digest TEXT
    """)

    # L1 structured: 5W-format summary for Tier-A output (~300 tokens)
    op.execute(f"""
        ALTER TABLE {schema}memory_units
        ADD COLUMN IF NOT EXISTS l1_structured TEXT
    """)

    # Importance score: 0-100, decays daily, boosted on access/update
    op.execute(f"""
        ALTER TABLE {schema}memory_units
        ADD COLUMN IF NOT EXISTS importance_score REAL DEFAULT 50.0
    """)

    # Maturity tier: lifecycle stage for importance-based filtering
    op.execute(f"""
        ALTER TABLE {schema}memory_units
        ADD COLUMN IF NOT EXISTS maturity VARCHAR(20) DEFAULT 'draft'
    """)

    # Index for importance decay cron job (skip stale facts)
    op.execute(f"""
        CREATE INDEX IF NOT EXISTS ix_memory_units_importance
        ON {schema}memory_units (importance_score)
        WHERE maturity != 'stale'
    """)


def downgrade() -> None:
    schema = _get_schema_prefix()

    op.execute(f"DROP INDEX IF EXISTS {schema}ix_memory_units_importance")
    op.execute(f"ALTER TABLE {schema}memory_units DROP COLUMN IF EXISTS maturity")
    op.execute(f"ALTER TABLE {schema}memory_units DROP COLUMN IF EXISTS importance_score")
    op.execute(f"ALTER TABLE {schema}memory_units DROP COLUMN IF EXISTS l1_structured")
    op.execute(f"ALTER TABLE {schema}memory_units DROP COLUMN IF EXISTS l0_digest")
