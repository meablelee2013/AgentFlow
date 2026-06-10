"""add_credentials_table

Revision ID: d8be28379deb
Revises: 6b7de2bc9ce1
Create Date: 2026-06-09 16:41:19.827776

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8be28379deb'
down_revision: Union[str, Sequence[str], None] = '6b7de2bc9ce1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — add credentials table."""
    op.create_table('credentials',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False,
              comment="Human-readable label, e.g. 'GitHub Token', 'Company ERP'"),
    sa.Column('auth_type', sa.String(length=20), nullable=False,
              comment='bearer | api_key | basic | login_flow'),
    sa.Column('encrypted_data', sa.Text(), nullable=False,
              comment='Fernet-encrypted JSON blob holding the actual secrets'),
    sa.Column('user_id', sa.UUID(), nullable=False,
              comment='Owning user — client-side UUID (future: FK → users.id)'),
    sa.Column('cached_token', sa.Text(), nullable=True,
              comment='Fernet-encrypted cached access token (login_flow only)'),
    sa.Column('cached_token_expires_at', sa.DateTime(timezone=True), nullable=True,
              comment='When the cached token expires'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_credentials_auth_type'), 'credentials', ['auth_type'], unique=False)
    op.create_index(op.f('ix_credentials_user_id'), 'credentials', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema — drop credentials table."""
    op.drop_index(op.f('ix_credentials_user_id'), table_name='credentials')
    op.drop_index(op.f('ix_credentials_auth_type'), table_name='credentials')
    op.drop_table('credentials')
