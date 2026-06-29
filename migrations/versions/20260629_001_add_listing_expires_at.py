"""Add listing expires_at column with backfill for 7-day automatic expiration.

Revision ID: 20260629_001
Revises: 20260620_001
Create Date: 2026-06-29

Adds persistent expires_at = created_at + 7 days.
All public queries will filter on (is_active, expires_at).
Zero-downtime strategy: nullable -> backfill -> NOT NULL -> index.
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision = '20260629_001'
down_revision = '20260620_001'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add column as nullable (safe on prod, no lock for most DBs)
    op.add_column('listings', sa.Column('expires_at', sa.DateTime(), nullable=True))

    # 2. Backfill: give every existing row its original 7-day lifetime based on created_at.
    #    Dialect-aware to support both SQLite (dev) and PostgreSQL (prod).
    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect == 'postgresql':
        # Postgres supports INTERVAL directly
        op.execute(
            "UPDATE listings SET expires_at = created_at + INTERVAL '7 days' "
            "WHERE expires_at IS NULL"
        )
    else:
        # SQLite (and most others): datetime() modifier
        op.execute(
            "UPDATE listings SET expires_at = datetime(created_at, '+7 days') "
            "WHERE expires_at IS NULL"
        )

    # 3. Make the column NOT NULL now that data is populated.
    #    SQLite requires batch_alter_table for column nullability change.
    if dialect == 'sqlite':
        with op.batch_alter_table('listings') as batch_op:
            batch_op.alter_column('expires_at', nullable=False)
    else:
        op.alter_column('listings', 'expires_at', nullable=False)

    # 4. Performance index: composite on (is_active, expires_at) as specified.
    #    Also keep a single-column index on expires_at (added by model declaration via create_all path).
    #    Name chosen to be descriptive and avoid conflicts.
    op.create_index(
        'ix_listings_is_active_expires_at',
        'listings',
        ['is_active', 'expires_at'],
        unique=False
    )

    # Optional: standalone index on expires_at for other queries (safe + cheap)
    # The model already declares index=True so it will be present after model use.
    # Explicit here ensures migration owns it for clean downgrade.
    op.create_index(
        op.f('ix_listings_expires_at'),
        'listings',
        ['expires_at'],
        unique=False
    )


def downgrade():
    # Drop indexes first (reverse order)
    op.drop_index(op.f('ix_listings_expires_at'), table_name='listings')
    op.drop_index('ix_listings_is_active_expires_at', table_name='listings')

    # Drop column (nullable was true during life, safe)
    op.drop_column('listings', 'expires_at')