"""Add user_ai_usage table for daily Grok chat free quota tracking

Revision ID: 20260620_001
Revises: 
Create Date: 2026-06-20

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260620_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'user_ai_usage',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('usage_date', sa.Date(), nullable=False),
        sa.Column('free_chat_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_ai_calls', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_ai_call_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=True, onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'usage_date', name='uq_user_ai_usage_date'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    )
    op.create_index(op.f('ix_user_ai_usage_user_id'), 'user_ai_usage', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_ai_usage_usage_date'), 'user_ai_usage', ['usage_date'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_user_ai_usage_usage_date'), table_name='user_ai_usage')
    op.drop_index(op.f('ix_user_ai_usage_user_id'), table_name='user_ai_usage')
    op.drop_table('user_ai_usage')
