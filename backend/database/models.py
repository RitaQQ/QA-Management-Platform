"""
SQLAlchemy ORM models for the QA Platform.

Multi-tenant design: all business tables include a tenant_id column
referencing the organizations table, enabling data isolation per tenant.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, DateTime,
    ForeignKey, UniqueConstraint, Index, BigInteger,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.postgresql import UUID

Base = declarative_base()


def utcnow():
    """Return the current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Organization (tenant root)
# ---------------------------------------------------------------------------

class Organization(Base):
    __tablename__ = 'organizations'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False)
    plan = Column(String(50), default='trial')  # trial/free/pro/enterprise
    trial_ends_at = Column(DateTime(timezone=True))
    subscription_status = Column(String(50), default='trialing')  # trialing/active/expired

    # Jira integration
    jira_site_url = Column(Text)
    jira_access_token = Column(Text)
    jira_refresh_token = Column(Text)
    jira_token_expires_at = Column(DateTime(timezone=True))
    jira_cloud_id = Column(String(255))
    jira_user_email = Column(String(255))
    jira_api_token = Column(Text)

    # Payment (Phase 2)
    payment_provider = Column(String(50))
    payment_customer_id = Column(String(255))

    # Notifications
    notification_email = Column(Text)
    notification_webhook_url = Column(Text)

    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    users = relationship('User', back_populates='organization', cascade='all, delete-orphan')
    api_endpoints = relationship('ApiEndpoint', back_populates='organization', cascade='all, delete-orphan')


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = 'users'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey('organizations.id', ondelete='CASCADE'),
        nullable=False,
    )
    username = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    password_hash = Column(Text, nullable=False)
    role = Column(String(50), default='user')  # admin/user
    is_active = Column(Boolean, default=True)
    last_login_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint('tenant_id', 'username', name='uq_users_tenant_username'),
        UniqueConstraint('tenant_id', 'email', name='uq_users_tenant_email'),
    )

    organization = relationship('Organization', back_populates='users')


# ---------------------------------------------------------------------------
# API Monitoring
# ---------------------------------------------------------------------------

class ApiEndpoint(Base):
    __tablename__ = 'api_endpoints'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey('organizations.id', ondelete='CASCADE'),
        nullable=False,
    )
    name = Column(String(255), nullable=False)
    url = Column(Text, nullable=False)
    method = Column(String(10), default='GET')
    request_body = Column(Text)
    headers = Column(Text)  # JSON string
    expected_status_code = Column(Integer, default=200)
    check_interval_seconds = Column(Integer, default=60)
    status = Column(String(50), default='unknown')  # healthy/unhealthy/unknown
    response_time = Column(Float, default=0)
    last_check = Column(DateTime(timezone=True))
    error_count = Column(Integer, default=0)
    last_error = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index('idx_api_endpoints_tenant', 'tenant_id'),
    )

    organization = relationship('Organization', back_populates='api_endpoints')
    check_history = relationship(
        'ApiCheckHistory', back_populates='api_endpoint', cascade='all, delete-orphan',
    )
    testcase_links = relationship(
        'ApiTestcaseLink', back_populates='api_endpoint', cascade='all, delete-orphan',
    )


class ApiCheckHistory(Base):
    __tablename__ = 'api_check_history'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    api_id = Column(
        Integer,
        ForeignKey('api_endpoints.id', ondelete='CASCADE'),
        nullable=False,
    )
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey('organizations.id', ondelete='CASCADE'),
        nullable=False,
    )
    status = Column(String(50), nullable=False)
    status_code = Column(Integer)
    response_time_ms = Column(Integer)
    error_message = Column(Text)
    checked_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index('idx_api_check_history_api_time', 'api_id', 'checked_at'),
        Index('idx_api_check_history_tenant', 'tenant_id', 'checked_at'),
    )

    api_endpoint = relationship('ApiEndpoint', back_populates='check_history')


# ---------------------------------------------------------------------------
# Product Tags
# ---------------------------------------------------------------------------

class ProductTag(Base):
    __tablename__ = 'product_tags'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey('organizations.id', ondelete='CASCADE'),
        nullable=False,
    )
    name = Column(String(255), nullable=False)
    description = Column(Text)
    color = Column(String(7), default='#007bff')
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint('tenant_id', 'name', name='uq_product_tags_tenant_name'),
    )


# ---------------------------------------------------------------------------
# Test Projects
# ---------------------------------------------------------------------------

class TestProject(Base):
    __tablename__ = 'test_projects'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey('organizations.id', ondelete='CASCADE'),
        nullable=False,
    )
    name = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(String(50), default='draft')  # draft/in_progress/completed
    responsible_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
    )
    start_time = Column(DateTime(timezone=True))
    end_time = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint('tenant_id', 'name', name='uq_test_projects_tenant_name'),
    )

    responsible_user = relationship('User')
    test_results = relationship(
        'TestResult', back_populates='project', cascade='all, delete-orphan',
    )


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

class TestCase(Base):
    __tablename__ = 'test_cases'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey('organizations.id', ondelete='CASCADE'),
        nullable=False,
    )
    tc_id = Column(String(20), nullable=False)  # TC00001 format
    title = Column(String(500), nullable=False)
    user_role = Column(Text)
    feature_description = Column(Text)
    acceptance_criteria = Column(Text)
    test_notes = Column(Text)
    priority = Column(String(20), default='medium')  # low/medium/high
    status = Column(String(20), default='draft')  # draft/ready/in_progress/completed/blocked
    test_project_id = Column(
        Integer, ForeignKey('test_projects.id', ondelete='SET NULL'),
    )
    responsible_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
    )
    estimated_hours = Column(Float, default=0)
    actual_hours = Column(Float, default=0)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint('tenant_id', 'tc_id', name='uq_test_cases_tenant_tcid'),
        Index('idx_test_cases_tenant', 'tenant_id'),
        Index('idx_test_cases_project', 'test_project_id'),
    )

    test_project = relationship('TestProject')
    responsible_user = relationship('User')
    tags = relationship('ProductTag', secondary='test_case_tags')
    api_links = relationship(
        'ApiTestcaseLink', back_populates='test_case', cascade='all, delete-orphan',
    )
    jira_links = relationship('JiraIssueLink', back_populates='test_case')


# ---------------------------------------------------------------------------
# Test Case Tags (association table)
# ---------------------------------------------------------------------------

class TestCaseTag(Base):
    __tablename__ = 'test_case_tags'

    test_case_id = Column(
        Integer, ForeignKey('test_cases.id', ondelete='CASCADE'), primary_key=True,
    )
    product_tag_id = Column(
        Integer, ForeignKey('product_tags.id', ondelete='CASCADE'), primary_key=True,
    )


# ---------------------------------------------------------------------------
# Test Results
# ---------------------------------------------------------------------------

class TestResult(Base):
    __tablename__ = 'test_results'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey('organizations.id', ondelete='CASCADE'),
        nullable=False,
    )
    project_id = Column(
        Integer, ForeignKey('test_projects.id', ondelete='CASCADE'), nullable=False,
    )
    test_case_id = Column(
        Integer, ForeignKey('test_cases.id', ondelete='CASCADE'), nullable=False,
    )
    status = Column(String(20), default='not_tested')  # pass/fail/blocked/not_tested
    notes = Column(Text)
    known_issues = Column(Text)
    blocked_reason = Column(Text)
    tested_at = Column(DateTime(timezone=True), default=utcnow)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint('project_id', 'test_case_id', name='uq_test_results_project_case'),
        Index('idx_test_results_project', 'project_id'),
    )

    project = relationship('TestProject', back_populates='test_results')
    test_case = relationship('TestCase')
    jira_links = relationship('JiraIssueLink', back_populates='test_result')


# ---------------------------------------------------------------------------
# API <-> TestCase link (many-to-many with metadata)
# ---------------------------------------------------------------------------

class ApiTestcaseLink(Base):
    __tablename__ = 'api_testcase_links'

    api_id = Column(
        Integer, ForeignKey('api_endpoints.id', ondelete='CASCADE'), primary_key=True,
    )
    test_case_id = Column(
        Integer, ForeignKey('test_cases.id', ondelete='CASCADE'), primary_key=True,
    )
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey('organizations.id', ondelete='CASCADE'),
        nullable=False,
    )
    link_type = Column(String(50), default='covers')
    created_at = Column(DateTime(timezone=True), default=utcnow)

    api_endpoint = relationship('ApiEndpoint', back_populates='testcase_links')
    test_case = relationship('TestCase', back_populates='api_links')


# ---------------------------------------------------------------------------
# Jira Issue Links
# ---------------------------------------------------------------------------

class JiraIssueLink(Base):
    __tablename__ = 'jira_issue_links'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey('organizations.id', ondelete='CASCADE'),
        nullable=False,
    )
    test_case_id = Column(Integer, ForeignKey('test_cases.id', ondelete='SET NULL'))
    test_result_id = Column(Integer, ForeignKey('test_results.id', ondelete='SET NULL'))
    jira_issue_key = Column(String(50), nullable=False)  # e.g. PROJ-123
    jira_issue_summary = Column(Text)
    jira_status = Column(String(100))
    jira_assignee = Column(String(255))
    jira_priority = Column(String(50))
    last_synced_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index('idx_jira_links_tenant', 'tenant_id'),
        Index('idx_jira_links_issue_key', 'jira_issue_key'),
    )

    test_case = relationship('TestCase', back_populates='jira_links')
    test_result = relationship('TestResult', back_populates='jira_links')


# ---------------------------------------------------------------------------
# Invite Links
# ---------------------------------------------------------------------------

class InviteLink(Base):
    __tablename__ = 'invite_links'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey('organizations.id', ondelete='CASCADE'),
        nullable=False,
    )
    token = Column(String(64), unique=True, nullable=False)
    role = Column(String(50), default='user')
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
    )
    max_uses = Column(Integer)  # null = unlimited
    use_count = Column(Integer, default=0)
    expires_at = Column(DateTime(timezone=True))  # null = never expires
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index('idx_invite_links_token', 'token', unique=True),
        Index('idx_invite_links_tenant', 'tenant_id'),
    )

    organization = relationship('Organization')
    creator = relationship('User')
