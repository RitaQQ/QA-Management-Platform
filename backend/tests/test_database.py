"""
Database schema verification tests.

These tests validate that the PostgreSQL database has all required tables,
columns, indexes, and constraints after running Alembic migrations.
"""
import pytest
from sqlalchemy import inspect

from database.models import Base


@pytest.fixture(scope='module')
def inspector(db_engine):
    """Return a database inspector for schema introspection."""
    return inspect(db_engine)


# ---------------------------------------------------------------------------
# Table existence
# ---------------------------------------------------------------------------

REQUIRED_TABLES = [
    'organizations',
    'users',
    'api_endpoints',
    'api_check_history',
    'test_cases',
    'test_case_tags',
    'product_tags',
    'test_projects',
    'test_results',
    'api_testcase_links',
    'jira_issue_links',
]


def test_all_tables_exist(inspector):
    """All 11 business tables must be present in the database."""
    tables = inspector.get_table_names()
    for table in REQUIRED_TABLES:
        assert table in tables, f"Missing table: {table}"


# ---------------------------------------------------------------------------
# Organization / tenant columns
# ---------------------------------------------------------------------------

def test_organizations_has_trial_fields(inspector):
    """Organizations table must include plan/subscription fields."""
    columns = {col['name'] for col in inspector.get_columns('organizations')}
    assert 'plan' in columns
    assert 'trial_ends_at' in columns
    assert 'subscription_status' in columns


def test_organizations_has_jira_fields(inspector):
    """Organizations table must include Jira integration fields."""
    columns = {col['name'] for col in inspector.get_columns('organizations')}
    for field in ['jira_site_url', 'jira_access_token', 'jira_refresh_token',
                  'jira_token_expires_at', 'jira_cloud_id']:
        assert field in columns, f"Missing Jira field: {field}"


# ---------------------------------------------------------------------------
# Test case specific columns
# ---------------------------------------------------------------------------

def test_test_cases_has_separated_fields(inspector):
    """Test cases must have user_role and feature_description columns."""
    columns = {col['name'] for col in inspector.get_columns('test_cases')}
    assert 'user_role' in columns
    assert 'feature_description' in columns


def test_test_cases_has_all_fields(inspector):
    """Test cases must have all required fields including acceptance_criteria."""
    columns = {col['name'] for col in inspector.get_columns('test_cases')}
    required = [
        'id', 'tenant_id', 'tc_id', 'title', 'user_role',
        'feature_description', 'acceptance_criteria', 'test_notes',
        'priority', 'status', 'test_project_id', 'responsible_user_id',
        'estimated_hours', 'actual_hours', 'created_at', 'updated_at',
    ]
    for field in required:
        assert field in columns, f"Missing test_cases field: {field}"


# ---------------------------------------------------------------------------
# Multi-tenant verification
# ---------------------------------------------------------------------------

TENANT_TABLES = [
    'users',
    'api_endpoints',
    'api_check_history',
    'test_cases',
    'product_tags',
    'test_projects',
    'test_results',
    'jira_issue_links',
    'api_testcase_links',
]


def test_tenant_id_on_all_business_tables(inspector):
    """Every business table must have a tenant_id column for data isolation."""
    for table in TENANT_TABLES:
        columns = {col['name'] for col in inspector.get_columns(table)}
        assert 'tenant_id' in columns, f"Missing tenant_id on: {table}"


# ---------------------------------------------------------------------------
# Index verification
# ---------------------------------------------------------------------------

def test_key_indexes_exist(inspector):
    """Critical performance indexes must be present."""
    # api_endpoints tenant index
    idx_names = {idx['name'] for idx in inspector.get_indexes('api_endpoints')}
    assert 'idx_api_endpoints_tenant' in idx_names

    # api_check_history composite indexes
    idx_names = {idx['name'] for idx in inspector.get_indexes('api_check_history')}
    assert 'idx_api_check_history_api_time' in idx_names
    assert 'idx_api_check_history_tenant' in idx_names

    # test_cases indexes
    idx_names = {idx['name'] for idx in inspector.get_indexes('test_cases')}
    assert 'idx_test_cases_tenant' in idx_names
    assert 'idx_test_cases_project' in idx_names

    # jira_issue_links indexes
    idx_names = {idx['name'] for idx in inspector.get_indexes('jira_issue_links')}
    assert 'idx_jira_links_tenant' in idx_names
    assert 'idx_jira_links_issue_key' in idx_names


# ---------------------------------------------------------------------------
# Unique constraint verification
# ---------------------------------------------------------------------------

def test_unique_constraints(inspector):
    """Critical unique constraints must be present."""
    # organizations.slug
    org_uqs = inspector.get_unique_constraints('organizations')
    org_uq_cols = [set(uq['column_names']) for uq in org_uqs]
    assert {'slug'} in org_uq_cols, "Missing unique constraint on organizations.slug"

    # users (tenant_id, username) and (tenant_id, email)
    user_uqs = inspector.get_unique_constraints('users')
    user_uq_cols = [set(uq['column_names']) for uq in user_uqs]
    assert {'tenant_id', 'username'} in user_uq_cols
    assert {'tenant_id', 'email'} in user_uq_cols

    # test_cases (tenant_id, tc_id)
    tc_uqs = inspector.get_unique_constraints('test_cases')
    tc_uq_cols = [set(uq['column_names']) for uq in tc_uqs]
    assert {'tenant_id', 'tc_id'} in tc_uq_cols


# ---------------------------------------------------------------------------
# Foreign key verification
# ---------------------------------------------------------------------------

def test_foreign_keys_on_users(inspector):
    """Users table must reference organizations with CASCADE delete."""
    fks = inspector.get_foreign_keys('users')
    org_fk = [fk for fk in fks if fk['referred_table'] == 'organizations']
    assert len(org_fk) == 1
    assert org_fk[0]['referred_columns'] == ['id']
    assert org_fk[0]['options'].get('ondelete', '').upper() == 'CASCADE'


def test_alembic_version_table_exists(inspector):
    """Alembic version tracking table must exist after migration."""
    tables = inspector.get_table_names()
    assert 'alembic_version' in tables
