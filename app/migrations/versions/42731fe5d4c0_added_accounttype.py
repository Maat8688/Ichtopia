"""Added AccountType

Revision ID: 42731fe5d4c0
Revises: 6c193441aab5
Create Date: 2024-10-27 11:57:28.052665

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '42731fe5d4c0'
down_revision = '6c193441aab5'
branch_labels = None
depends_on = None


def upgrade():
    # Deze migratie is met opzet leeg.
    #
    # Alembic had hier ooit automatisch `op.drop_table('user')` van
    # gemaakt, omdat de modellen op dat moment niet gevonden werden. Dat is nooit
    # zo gedraaid - de tabellen worden in productie aangemaakt door db.create_all()
    # - maar het stond wel klaar: wie ooit `flask db upgrade` draaide op een
    # database zonder alembic-geschiedenis, gooide daarmee alle accounts weg.
    # Leeggemaakt zodat dat niet meer kan.
    pass


def downgrade():
    pass
