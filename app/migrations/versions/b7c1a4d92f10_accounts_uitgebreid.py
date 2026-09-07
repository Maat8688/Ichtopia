"""Ruimere wachtwoordkolom en aanmaakdatum bij een account

Revision ID: b7c1a4d92f10
Revises: fd5c7683777f
Create Date: 2026-09-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7c1a4d92f10'
down_revision = 'fd5c7683777f'
branch_labels = None
depends_on = None


def kolommen(tabel: str) -> set[str]:
    """Welke kolommen heeft deze tabel nu?

    De app maakt tabellen ook zelf aan met db.create_all(), dus een kolom kan
    er al staan zonder dat deze migratie gedraaid is. Daarom overal eerst
    kijken in plaats van blind toevoegen.
    """
    inspector = sa.inspect(op.get_bind())
    if tabel not in inspector.get_table_names():
        return set()
    return {kolom['name'] for kolom in inspector.get_columns(tabel)}


def upgrade():
    bestaand = kolommen('user')
    if not bestaand:
        # Geen user-tabel: die maakt de app zelf aan bij het opstarten.
        return

    # batch_alter_table zodat dit ook op SQLite werkt (de tests draaien daarop);
    # op Postgres komt er gewoon een ALTER TABLE uit.
    with op.batch_alter_table('user') as batch:
        # De hash van werkzeug (scrypt) is ruim langer dan 128 tekens; in de
        # oude kolom paste hij niet en mislukte het opslaan van een account.
        batch.alter_column('password_hash',
                           existing_type=sa.String(length=128),
                           type_=sa.String(length=255),
                           existing_nullable=False)
        if 'created_at' not in bestaand:
            batch.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))

    if 'created_at' not in bestaand:
        # Bestaande accounts krijgen de datum van de migratie.
        op.execute('UPDATE "user" SET created_at = CURRENT_TIMESTAMP '
                   'WHERE created_at IS NULL')
        with op.batch_alter_table('user') as batch:
            batch.alter_column('created_at', existing_type=sa.DateTime(),
                               nullable=False)


def downgrade():
    heeftDatum = 'created_at' in kolommen('user')
    with op.batch_alter_table('user') as batch:
        if heeftDatum:
            batch.drop_column('created_at')
        batch.alter_column('password_hash',
                           existing_type=sa.String(length=255),
                           type_=sa.String(length=128),
                           existing_nullable=False)
