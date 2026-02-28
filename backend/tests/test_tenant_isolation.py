"""
Tests for multi-tenant data isolation.

Verifies that:
- Each tenant sees only its own data.
- Tenant A cannot read, update, or delete Tenant B's records.
- Newly created records are automatically scoped to the calling tenant.
- Different tenants may reuse the same ``tc_id`` without conflict.
"""
import pytest
from datetime import datetime, timedelta, timezone

from app_factory import create_app
from database.models import Organization, User, TestCase, ApiEndpoint
from database.session import SessionLocal
from services.user_service import hash_password
from middleware.auth import create_access_token


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def app():
    """Create a Flask test application for the module."""
    app = create_app(testing=True)
    yield app


@pytest.fixture(scope='module')
def two_tenants(app):
    """Create two isolated tenants with seed data and JWT tokens.

    Returns a dict with org IDs, tokens, and record IDs for both tenants.
    """
    db = SessionLocal()
    try:
        # Clean related tables in dependency order
        db.query(TestCase).delete()
        db.query(ApiEndpoint).delete()
        db.query(User).delete()
        db.query(Organization).delete()
        db.commit()

        # -- Tenant A ---------------------------------------------------------
        org_a = Organization(
            name='Tenant A',
            slug='tenant-a',
            plan='trial',
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
            subscription_status='trialing',
        )
        db.add(org_a)
        db.flush()

        user_a = User(
            tenant_id=org_a.id,
            username='user_a',
            email='a@test.com',
            password_hash=hash_password('Password123!'),
            role='admin',
        )
        db.add(user_a)
        db.flush()

        case_a = TestCase(
            tenant_id=org_a.id,
            tc_id='TC00001',
            title='Tenant A Test Case',
            priority='high',
            status='draft',
        )
        db.add(case_a)

        api_a = ApiEndpoint(
            tenant_id=org_a.id,
            name='Tenant A API',
            url='https://a.example.com/api',
        )
        db.add(api_a)

        # -- Tenant B ---------------------------------------------------------
        org_b = Organization(
            name='Tenant B',
            slug='tenant-b',
            plan='trial',
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
            subscription_status='trialing',
        )
        db.add(org_b)
        db.flush()

        user_b = User(
            tenant_id=org_b.id,
            username='user_b',
            email='b@test.com',
            password_hash=hash_password('Password123!'),
            role='admin',
        )
        db.add(user_b)
        db.flush()

        case_b = TestCase(
            tenant_id=org_b.id,
            tc_id='TC00001',
            title='Tenant B Test Case',
            priority='medium',
            status='draft',
        )
        db.add(case_b)

        db.commit()

        # Refresh to get auto-generated IDs
        db.refresh(case_a)
        db.refresh(case_b)
        db.refresh(api_a)

        token_a = create_access_token(str(user_a.id), str(org_a.id), 'admin')
        token_b = create_access_token(str(user_b.id), str(org_b.id), 'admin')

        yield {
            'org_a_id': str(org_a.id),
            'org_b_id': str(org_b.id),
            'token_a': token_a,
            'token_b': token_b,
            'case_a_id': case_a.id,
            'case_b_id': case_b.id,
            'api_a_id': api_a.id,
        }
    finally:
        db.close()


@pytest.fixture
def client(app):
    """Return a Flask test client."""
    return app.test_client()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _auth(token):
    """Build an Authorization header dict."""
    return {'Authorization': f'Bearer {token}'}


# ---------------------------------------------------------------------------
# Read isolation tests
# ---------------------------------------------------------------------------

class TestReadIsolation:
    """Tenant A and Tenant B should only see their own records."""

    def test_tenant_a_only_sees_own_cases(self, client, two_tenants):
        resp = client.get(
            '/api/test-isolation/cases',
            headers=_auth(two_tenants['token_a']),
        )
        assert resp.status_code == 200
        cases = resp.get_json()['data']
        assert len(cases) >= 1
        titles = [c['title'] for c in cases]
        assert 'Tenant A Test Case' in titles
        assert 'Tenant B Test Case' not in titles

    def test_tenant_b_only_sees_own_cases(self, client, two_tenants):
        resp = client.get(
            '/api/test-isolation/cases',
            headers=_auth(two_tenants['token_b']),
        )
        assert resp.status_code == 200
        cases = resp.get_json()['data']
        assert len(cases) >= 1
        titles = [c['title'] for c in cases]
        assert 'Tenant B Test Case' in titles
        assert 'Tenant A Test Case' not in titles


# ---------------------------------------------------------------------------
# Write isolation tests
# ---------------------------------------------------------------------------

class TestWriteIsolation:
    """Cross-tenant mutations must be prevented."""

    def test_tenant_a_cannot_update_tenant_b_case(self, client, two_tenants):
        """PUT from Tenant A targeting Tenant B's case ID returns 404."""
        resp = client.put(
            f'/api/test-isolation/cases/{two_tenants["case_b_id"]}',
            json={'title': 'Hacked by A!'},
            headers=_auth(two_tenants['token_a']),
        )
        assert resp.status_code == 404

    def test_tenant_b_cannot_update_tenant_a_case(self, client, two_tenants):
        """PUT from Tenant B targeting Tenant A's case ID returns 404."""
        resp = client.put(
            f'/api/test-isolation/cases/{two_tenants["case_a_id"]}',
            json={'title': 'Hacked by B!'},
            headers=_auth(two_tenants['token_b']),
        )
        assert resp.status_code == 404

    def test_tenant_a_cannot_delete_tenant_b_case(self, client, two_tenants):
        """DELETE from Tenant A targeting Tenant B's case ID returns 404."""
        resp = client.delete(
            f'/api/test-isolation/cases/{two_tenants["case_b_id"]}',
            headers=_auth(two_tenants['token_a']),
        )
        assert resp.status_code == 404

    def test_original_data_unchanged_after_cross_tenant_attempts(self, client, two_tenants):
        """After failed cross-tenant mutations the original data is intact."""
        resp = client.get(
            '/api/test-isolation/cases',
            headers=_auth(two_tenants['token_b']),
        )
        cases = resp.get_json()['data']
        original = [c for c in cases if c['id'] == two_tenants['case_b_id']]
        assert len(original) == 1
        assert original[0]['title'] == 'Tenant B Test Case'


# ---------------------------------------------------------------------------
# Auto-scoping tests
# ---------------------------------------------------------------------------

class TestAutoScoping:
    """New records must be automatically scoped to the calling tenant."""

    def test_new_case_gets_correct_tenant_id(self, client, two_tenants):
        resp = client.post(
            '/api/test-isolation/cases',
            json={'title': 'New Case by A', 'priority': 'low'},
            headers=_auth(two_tenants['token_a']),
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['title'] == 'New Case by A'

        # Verify tenant_id in the database
        db = SessionLocal()
        try:
            case = db.query(TestCase).filter_by(id=data['id']).first()
            assert case is not None
            assert str(case.tenant_id) == two_tenants['org_a_id']
        finally:
            db.close()

    def test_new_case_not_visible_to_other_tenant(self, client, two_tenants):
        """A record created by Tenant A must not appear in Tenant B's list."""
        # Create as Tenant A
        client.post(
            '/api/test-isolation/cases',
            json={'title': 'Secret A case'},
            headers=_auth(two_tenants['token_a']),
        )

        # List as Tenant B
        resp = client.get(
            '/api/test-isolation/cases',
            headers=_auth(two_tenants['token_b']),
        )
        titles = [c['title'] for c in resp.get_json()['data']]
        assert 'Secret A case' not in titles


# ---------------------------------------------------------------------------
# TC ID namespace tests
# ---------------------------------------------------------------------------

class TestTcIdNamespace:
    """tc_id is unique per tenant, not globally."""

    def test_same_tc_id_different_tenants(self, client, two_tenants):
        """Both tenants can have TC00001 without conflict."""
        resp_a = client.get(
            '/api/test-isolation/cases',
            headers=_auth(two_tenants['token_a']),
        )
        resp_b = client.get(
            '/api/test-isolation/cases',
            headers=_auth(two_tenants['token_b']),
        )

        tc_ids_a = [c['tc_id'] for c in resp_a.get_json()['data']]
        tc_ids_b = [c['tc_id'] for c in resp_b.get_json()['data']]

        assert 'TC00001' in tc_ids_a
        assert 'TC00001' in tc_ids_b

    def test_auto_tc_id_scoped_to_tenant(self, client, two_tenants):
        """Auto-generated tc_id counts only records within the same tenant."""
        # Tenant B creates a new case; its tc_id should be based on
        # Tenant B's existing count, not a global count.
        resp = client.post(
            '/api/test-isolation/cases',
            json={'title': 'Tenant B Second Case'},
            headers=_auth(two_tenants['token_b']),
        )
        assert resp.status_code == 201
        data = resp.get_json()
        # Tenant B already has TC00001 from setup, so next should be TC00002
        assert data['tc_id'] == 'TC00002'


# ---------------------------------------------------------------------------
# Unauthenticated access tests
# ---------------------------------------------------------------------------

class TestUnauthenticatedAccess:
    """Requests without a valid token must be rejected."""

    def test_no_token_returns_401(self, client):
        resp = client.get('/api/test-isolation/cases')
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self, client):
        resp = client.get(
            '/api/test-isolation/cases',
            headers={'Authorization': 'Bearer invalid.token.here'},
        )
        assert resp.status_code == 401
