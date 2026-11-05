"""Geen e-mail meer: de kolom wordt optioneel en alle adressen worden gewist

Een account is nu alleen een naam en een wachtwoord. We hebben niets aan het
e-mailadres en het is een persoonsgegeven van een kind, dus wordt alles wat er
al stond gewist. De kolom zelf blijft (leeg) bestaan, zodat er niets anders
aan de tabel hoeft te veranderen.

Revision ID: e2b4c6d8f0a1
Revises: c3f9a1207e44
Create Date: 2026-11-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e2b4c6d8f0a1'
down_revision = 'c3f9a1207e44'
branch_labels = None
depends_on = None


def heeftEmail() -> bool:
    inspector = sa.inspect(op.get_bind())
    if 'user' not in inspector.get_table_names():
        return False
    return any(kolom['name'] == 'email' for kolom in inspector.get_columns('user'))


def upgrade():
    if not heeftEmail():
        return
    # Eerst optioneel maken, dan pas leegmaken: andersom mag niet.
    with op.batch_alter_table('user') as batch:
        batch.alter_column('email', existing_type=sa.String(length=120), nullable=True)
    op.execute('UPDATE "user" SET email = NULL')


def downgrade():
    # De gewiste adressen komen niet terug. Verplicht maken kan dus ook niet
    # meer zonder ze te verzinnen; we laten de kolom zoals hij is.
    pass
