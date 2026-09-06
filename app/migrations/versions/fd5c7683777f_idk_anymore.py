"""Idk anymore

Revision ID: fd5c7683777f
Revises: 42731fe5d4c0
Create Date: 2024-10-27 13:02:46.729292

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'fd5c7683777f'
down_revision = '42731fe5d4c0'
branch_labels = None
depends_on = None


def upgrade():
    # Deze migratie is met opzet leeg.
    #
    # Alembic had hier ooit automatisch `op.drop_table('user en results')` van
    # gemaakt, omdat de modellen op dat moment niet gevonden werden. Dat is nooit
    # zo gedraaid - de tabellen worden in productie aangemaakt door db.create_all()
    # - maar het stond wel klaar: wie ooit `flask db upgrade` draaide op een
    # database zonder alembic-geschiedenis, gooide daarmee alle accounts weg.
    # Leeggemaakt zodat dat niet meer kan.
    pass


def downgrade():
    pass
