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


def upgrade():
    # De hash van werkzeug (scrypt) is ruim langer dan 128 tekens; in de oude
    # kolom paste hij niet en mislukte het opslaan van een account.
    op.alter_column('user', 'password_hash',
                    existing_type=sa.String(length=128),
                    type_=sa.String(length=255),
                    existing_nullable=False)
    op.add_column('user', sa.Column('created_at', sa.DateTime(), nullable=True))
    # Bestaande accounts krijgen de datum van de migratie.
    op.execute('UPDATE "user" SET created_at = NOW() WHERE created_at IS NULL')
    op.alter_column('user', 'created_at', nullable=False)


def downgrade():
    op.drop_column('user', 'created_at')
    op.alter_column('user', 'password_hash',
                    existing_type=sa.String(length=255),
                    type_=sa.String(length=128),
                    existing_nullable=False)
