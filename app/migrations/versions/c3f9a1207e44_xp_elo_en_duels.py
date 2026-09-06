"""XP, levels, elo en de duelgeschiedenis

Revision ID: c3f9a1207e44
Revises: b7c1a4d92f10
Create Date: 2026-09-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3f9a1207e44'
down_revision = 'b7c1a4d92f10'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user') as batch:
        batch.add_column(sa.Column('xp', sa.Integer(), nullable=False, server_default='0'))
        batch.add_column(sa.Column('xp_day', sa.Date(), nullable=True))
        batch.add_column(sa.Column('xp_today', sa.Integer(), nullable=False, server_default='0'))
        batch.add_column(sa.Column('rating', sa.Integer(), nullable=False, server_default='1000'))
        batch.add_column(sa.Column('duels_won', sa.Integer(), nullable=False, server_default='0'))
        batch.add_column(sa.Column('duels_lost', sa.Integer(), nullable=False, server_default='0'))
        batch.add_column(sa.Column('duels_drawn', sa.Integer(), nullable=False, server_default='0'))

    op.create_table(
        'duel_match',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('played_at', sa.DateTime(), nullable=False),
        sa.Column('map_name', sa.String(length=40), nullable=False),
        sa.Column('questions', sa.Integer(), nullable=False),
        sa.Column('rated', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('one_id', sa.Integer(), nullable=False),
        sa.Column('two_id', sa.Integer(), nullable=False),
        sa.Column('one_score', sa.Integer(), nullable=False),
        sa.Column('two_score', sa.Integer(), nullable=False),
        sa.Column('one_rating_before', sa.Integer(), nullable=False),
        sa.Column('two_rating_before', sa.Integer(), nullable=False),
        sa.Column('one_rating_after', sa.Integer(), nullable=False),
        sa.Column('two_rating_after', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['one_id'], ['user.id']),
        sa.ForeignKeyConstraint(['two_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_duel_match_played_at', 'duel_match', ['played_at'])
    op.create_index('ix_duel_match_one_id', 'duel_match', ['one_id'])
    op.create_index('ix_duel_match_two_id', 'duel_match', ['two_id'])


def downgrade():
    op.drop_index('ix_duel_match_two_id', table_name='duel_match')
    op.drop_index('ix_duel_match_one_id', table_name='duel_match')
    op.drop_index('ix_duel_match_played_at', table_name='duel_match')
    op.drop_table('duel_match')
    with op.batch_alter_table('user') as batch:
        for column in ('duels_drawn', 'duels_lost', 'duels_won', 'rating',
                       'xp_today', 'xp_day', 'xp'):
            batch.drop_column(column)
