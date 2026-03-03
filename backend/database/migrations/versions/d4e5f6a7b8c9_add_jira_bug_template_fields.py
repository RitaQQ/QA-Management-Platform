"""Add Jira bug template fields to organizations.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""
from typing import Union
from alembic import op
import sqlalchemy as sa

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column('organizations', sa.Column('jira_bug_title_template', sa.Text(), nullable=True))
    op.add_column('organizations', sa.Column('jira_bug_description_template', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('organizations', 'jira_bug_description_template')
    op.drop_column('organizations', 'jira_bug_title_template')
