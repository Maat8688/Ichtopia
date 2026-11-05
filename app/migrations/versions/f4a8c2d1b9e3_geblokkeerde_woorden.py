"""Geblokkeerde woorden: extra woorden voor het naamfilter, via /beheer

Revision ID: f4a8c2d1b9e3
Revises: e2b4c6d8f0a1
Create Date: 2026-11-05 12:00:00.000000

Raakt geen enkele bestaande tabel aan; er komt alleen een tabel bij. Heeft
db.create_all() hem bij het opstarten al gemaakt, dan doet dit niets.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f4a8c2d1b9e3'
down_revision = 'e2b4c6d8f0a1'
branch_labels = None
depends_on = None


def upgrade():
    if 'geblokkeerd_woord' in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        'geblokkeerd_woord',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('woord', sa.String(length=40), nullable=False),
        sa.Column('toegevoegd_op', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('woord'),
    )


def downgrade():
    # Alleen deze tabel; accounts en statistieken blijven staan.
    if 'geblokkeerd_woord' in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table('geblokkeerd_woord')
