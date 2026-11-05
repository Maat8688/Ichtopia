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

NIEUWE_KOLOMMEN = [
    sa.Column('xp', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('xp_day', sa.Date(), nullable=True),
    sa.Column('xp_today', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('rating', sa.Integer(), nullable=False, server_default='1000'),
    sa.Column('duels_won', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('duels_lost', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('duels_drawn', sa.Integer(), nullable=False, server_default='0'),
]


def bestaandeKolommen(tabel: str) -> set[str]:
    """Zie de vorige migratie: db.create_all() kan hier al werk gedaan hebben."""
    inspector = sa.inspect(op.get_bind())
    if tabel not in inspector.get_table_names():
        return set()
    return {kolom['name'] for kolom in inspector.get_columns(tabel)}


def tabelBestaat(tabel: str) -> bool:
    return tabel in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    bestaand = bestaandeKolommen('user')
    if bestaand:
        ontbreekt = [kolom for kolom in NIEUWE_KOLOMMEN if kolom.name not in bestaand]
        if ontbreekt:
            with op.batch_alter_table('user') as batch:
                for kolom in ontbreekt:
                    batch.add_column(kolom)

    if not tabelBestaat('duel_match'):
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
    if tabelBestaat('duel_match'):
        op.drop_index('ix_duel_match_two_id', table_name='duel_match')
        op.drop_index('ix_duel_match_one_id', table_name='duel_match')
        op.drop_index('ix_duel_match_played_at', table_name='duel_match')
        op.drop_table('duel_match')
    bestaand = bestaandeKolommen('user')
    teVerwijderen = [k.name for k in reversed(NIEUWE_KOLOMMEN) if k.name in bestaand]
    if teVerwijderen:
        with op.batch_alter_table('user') as batch:
            for naam in teVerwijderen:
                batch.drop_column(naam)
