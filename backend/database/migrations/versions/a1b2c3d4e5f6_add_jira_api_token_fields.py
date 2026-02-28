"""add jira api token fields to organizations

Revision ID: a1b2c3d4e5f6
Revises: 742584645af3
Create Date: 2026-02-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '742584645af3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('organizations', sa.Column('jira_user_email', sa.String(255), nullable=True))
    op.add_column('organizations', sa.Column('jira_api_token', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('organizations', 'jira_api_token')
    op.drop_column('organizations', 'jira_user_email')
