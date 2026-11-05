"""Meldingen: feedback van bezoekers, te lezen op /beheer/meldingen

Revision ID: a7d3e9f2c6b1
Revises: f4a8c2d1b9e3
Create Date: 2026-11-05 15:00:00.000000

Raakt geen enkele bestaande tabel aan; er komt alleen een tabel bij. Heeft
db.create_all() hem bij het opstarten al gemaakt, dan doet dit niets.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7d3e9f2c6b1'
down_revision = 'f4a8c2d1b9e3'
branch_labels = None
depends_on = None


def upgrade():
    if 'melding' in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        'melding',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tijd', sa.DateTime(), nullable=False),
        sa.Column('soort', sa.String(length=10), nullable=False),
        sa.Column('reden', sa.String(length=20), nullable=True),
        sa.Column('tekst', sa.String(length=500), nullable=True),
        sa.Column('pagina', sa.String(length=80), nullable=True),
        sa.Column('kaart', sa.String(length=40), nullable=True),
        sa.Column('vraag', sa.String(length=80), nullable=True),
        sa.Column('antwoord', sa.String(length=80), nullable=True),
        sa.Column('afgehandeld', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_melding_tijd', 'melding', ['tijd'])


def downgrade():
    # Alleen deze tabel; accounts en statistieken blijven staan.
    if 'melding' in sa.inspect(op.get_bind()).get_table_names():
        op.drop_index('ix_melding_tijd', table_name='melding')
        op.drop_table('melding')
