"""Create token_usage table for Precision-per-Token accounting

Revision ID: l8g9h0i1j2k3
Revises: k6f7g8h9i0j1
Create Date: 2026-04-08

Tracks per-operation token consumption (retain/recall/reflect) to measure
and optimize the context tokens returned to agents.
"""

from collections.abc import Sequence

from alembic import context, op

# revision identifiers, used by Alembic.
revision: str = "l8g9h0i1j2k3"
down_revision: str | Sequence[str] | None = "k6f7g8h9i0j1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _get_schema_prefix() -> str:
    """Get schema prefix for table names (required for multi-tenant support)."""
    schema = context.config.get_main_option("target_schema")
    return f'"{schema}".' if schema else ""


def upgrade() -> None:
    schema = _get_schema_prefix()

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}token_usage (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            bank_id TEXT NOT NULL,
            operation VARCHAR(20) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            llm_input_tokens INTEGER DEFAULT 0,
            llm_output_tokens INTEGER DEFAULT 0,
            context_tokens INTEGER DEFAULT 0,
            query_tier VARCHAR(10),
            candidate_count INTEGER,
            novelty_rejected INTEGER,
            baseline_tokens INTEGER,
            saved_tokens INTEGER
        )
    """)

    # Query by bank + time range (dashboard trends)
    op.execute(f"""
        CREATE INDEX IF NOT EXISTS ix_token_usage_bank_time
        ON {schema}token_usage (bank_id, created_at DESC)
    """)

    # Query by operation type (aggregate by retain/recall/reflect)
    op.execute(f"""
        CREATE INDEX IF NOT EXISTS ix_token_usage_operation
        ON {schema}token_usage (operation, created_at DESC)
    """)


def downgrade() -> None:
    schema = _get_schema_prefix()

    op.execute(f"DROP INDEX IF EXISTS {schema}ix_token_usage_operation")
    op.execute(f"DROP INDEX IF EXISTS {schema}ix_token_usage_bank_time")
    op.execute(f"DROP TABLE IF EXISTS {schema}token_usage")
