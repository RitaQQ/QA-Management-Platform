"""
Tests for the member invitation and management system.

Covers invite link CRUD, join-via-invite, member listing,
role changes, deactivation, and tenant isolation.
"""
import pytest
from datetime import datetime, timedelta, timezone

from app_factory import create_app
from database.models import Organization, User, InviteLink
from database.session import SessionLocal
from services.user_service import hash_password


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def app():
    """Create a Flask test app once per module."""
    from database.models import Base
    from database.session import engine
    # Ensure all tables exist (including invite_links)
    Base.metadata.create_all(bind=engine)

    app = create_app(testing=True)
    yield app


@pytest.fixture(autouse=True)
def _clean():
    """Clean all relevant tables before every test."""
    db = SessionLocal()
    try:
        db.query(InviteLink).delete()
        db.query(User).delete()
        db.query(Organization).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_auth(client):
    """Register an org+admin and return (access_token, org_id, user_id)."""
    resp = client.post('/api/auth/register', json={
        'org_name': 'Test Org',
        'username': 'admin1',
        'email': 'admin@test.com',
        'password': 'SecurePass123!',
    })
    data = resp.get_json()
    return data['access_token'], data['organization']['id'], data['user']['id']


def auth_headers(token):
    return {'Authorization': f'Bearer {token}'}


# ---------------------------------------------------------------------------
# Invite link creation
# ---------------------------------------------------------------------------

class TestCreateInviteLink:

    def test_creates_link(self, client, admin_auth):
        token, _, _ = admin_auth
        resp = client.post(
            '/api/members/invite-links',
            json={'role': 'user'},
            headers=auth_headers(token),
        )
        assert resp.status_code == 201
        data = resp.get_json()['data']
        assert data['role'] == 'user'
        assert data['is_active'] is True
        assert len(data['token']) > 20

    def test_creates_link_with_max_uses(self, client, admin_auth):
        token, _, _ = admin_auth
        resp = client.post(
            '/api/members/invite-links',
            json={'role': 'admin', 'max_uses': 5, 'expires_hours': 48},
            headers=auth_headers(token),
        )
        assert resp.status_code == 201
        data = resp.get_json()['data']
        assert data['max_uses'] == 5
        assert data['expires_at'] is not None

    def test_non_admin_cannot_create(self, client, admin_auth):
        admin_token, _, _ = admin_auth
        # Create invite and join as normal user
        resp = client.post(
            '/api/members/invite-links',
            json={'role': 'user'},
            headers=auth_headers(admin_token),
        )
        invite_token = resp.get_json()['data']['token']

        join_resp = client.post('/api/auth/join', json={
            'token': invite_token,
            'username': 'member1',
            'email': 'member1@test.com',
            'password': 'SecurePass123!',
        })
        member_token = join_resp.get_json()['access_token']

        # Member tries to create invite link
        resp = client.post(
            '/api/members/invite-links',
            json={'role': 'user'},
            headers=auth_headers(member_token),
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Invite link listing
# ---------------------------------------------------------------------------

class TestListInviteLinks:

    def test_lists_links(self, client, admin_auth):
        token, _, _ = admin_auth
        client.post('/api/members/invite-links', json={}, headers=auth_headers(token))
        client.post('/api/members/invite-links', json={}, headers=auth_headers(token))

        resp = client.get('/api/members/invite-links', headers=auth_headers(token))
        assert resp.status_code == 200
        assert len(resp.get_json()['data']) == 2


# ---------------------------------------------------------------------------
# Invite link revocation
# ---------------------------------------------------------------------------

class TestRevokeInviteLink:

    def test_revokes_link(self, client, admin_auth):
        token, _, _ = admin_auth
        create_resp = client.post('/api/members/invite-links', json={}, headers=auth_headers(token))
        link_id = create_resp.get_json()['data']['id']

        resp = client.delete(f'/api/members/invite-links/{link_id}', headers=auth_headers(token))
        assert resp.status_code == 200

        # Verify it's deactivated
        links_resp = client.get('/api/members/invite-links', headers=auth_headers(token))
        link = [l for l in links_resp.get_json()['data'] if l['id'] == link_id][0]
        assert link['is_active'] is False

    def test_revoke_nonexistent(self, client, admin_auth):
        token, _, _ = admin_auth
        import uuid
        resp = client.delete(
            f'/api/members/invite-links/{uuid.uuid4()}',
            headers=auth_headers(token),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Invite token validation (public)
# ---------------------------------------------------------------------------

class TestValidateInvite:

    def test_valid_token(self, client, admin_auth):
        admin_token, _, _ = admin_auth
        create_resp = client.post(
            '/api/members/invite-links',
            json={'role': 'user'},
            headers=auth_headers(admin_token),
        )
        invite_token = create_resp.get_json()['data']['token']

        resp = client.get(f'/api/auth/invite/{invite_token}')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['organization_name'] == 'Test Org'
        assert data['role'] == 'user'

    def test_invalid_token(self, client):
        resp = client.get('/api/auth/invite/totally-fake-token')
        assert resp.status_code == 400

    def test_revoked_token(self, client, admin_auth):
        admin_token, _, _ = admin_auth
        create_resp = client.post(
            '/api/members/invite-links',
            json={},
            headers=auth_headers(admin_token),
        )
        data = create_resp.get_json()['data']
        client.delete(f'/api/members/invite-links/{data["id"]}', headers=auth_headers(admin_token))

        resp = client.get(f'/api/auth/invite/{data["token"]}')
        assert resp.status_code == 400
        assert 'revoked' in resp.get_json()['error'].lower()


# ---------------------------------------------------------------------------
# Join via invite
# ---------------------------------------------------------------------------

class TestJoinViaInvite:

    def test_join_creates_user(self, client, admin_auth):
        admin_token, org_id, _ = admin_auth
        create_resp = client.post(
            '/api/members/invite-links',
            json={'role': 'user'},
            headers=auth_headers(admin_token),
        )
        invite_token = create_resp.get_json()['data']['token']

        resp = client.post('/api/auth/join', json={
            'token': invite_token,
            'username': 'newmember',
            'email': 'new@test.com',
            'password': 'SecurePass123!',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert 'access_token' in data
        assert data['user']['role'] == 'user'
        assert data['organization']['id'] == org_id

    def test_join_increments_use_count(self, client, admin_auth):
        admin_token, _, _ = admin_auth
        create_resp = client.post(
            '/api/members/invite-links',
            json={'role': 'user'},
            headers=auth_headers(admin_token),
        )
        invite_token = create_resp.get_json()['data']['token']

        client.post('/api/auth/join', json={
            'token': invite_token,
            'username': 'u1',
            'email': 'u1@test.com',
            'password': 'SecurePass123!',
        })

        # Check use_count
        links_resp = client.get('/api/members/invite-links', headers=auth_headers(admin_token))
        link = [l for l in links_resp.get_json()['data'] if l['token'] == invite_token][0]
        assert link['use_count'] == 1

    def test_join_with_max_uses_exceeded(self, client, admin_auth):
        admin_token, _, _ = admin_auth
        create_resp = client.post(
            '/api/members/invite-links',
            json={'role': 'user', 'max_uses': 1},
            headers=auth_headers(admin_token),
        )
        invite_token = create_resp.get_json()['data']['token']

        # First join
        client.post('/api/auth/join', json={
            'token': invite_token,
            'username': 'first',
            'email': 'first@test.com',
            'password': 'SecurePass123!',
        })

        # Second join should fail
        resp = client.post('/api/auth/join', json={
            'token': invite_token,
            'username': 'second',
            'email': 'second@test.com',
            'password': 'SecurePass123!',
        })
        assert resp.status_code == 400
        assert 'usage limit' in resp.get_json()['error'].lower()

    def test_join_with_expired_link(self, client, admin_auth):
        admin_token, _, _ = admin_auth
        # Create a link that's already expired (by directly setting expires_at)
        db = SessionLocal()
        try:
            import secrets
            link = InviteLink(
                tenant_id=admin_auth[1],
                token=secrets.token_urlsafe(32),
                role='user',
                created_by=admin_auth[2],
                expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )
            db.add(link)
            db.commit()
            expired_token = link.token
        finally:
            db.close()

        resp = client.post('/api/auth/join', json={
            'token': expired_token,
            'username': 'latecomer',
            'email': 'late@test.com',
            'password': 'SecurePass123!',
        })
        assert resp.status_code == 400
        assert 'expired' in resp.get_json()['error'].lower()

    def test_join_with_duplicate_email(self, client, admin_auth):
        admin_token, _, _ = admin_auth
        create_resp = client.post(
            '/api/members/invite-links',
            json={'role': 'user'},
            headers=auth_headers(admin_token),
        )
        invite_token = create_resp.get_json()['data']['token']

        # admin@test.com is already registered by admin_auth
        resp = client.post('/api/auth/join', json={
            'token': invite_token,
            'username': 'dup',
            'email': 'admin@test.com',
            'password': 'SecurePass123!',
        })
        assert resp.status_code == 400
        assert 'already registered' in resp.get_json()['error'].lower()

    def test_join_short_password_rejected(self, client, admin_auth):
        admin_token, _, _ = admin_auth
        create_resp = client.post(
            '/api/members/invite-links',
            json={},
            headers=auth_headers(admin_token),
        )
        invite_token = create_resp.get_json()['data']['token']

        resp = client.post('/api/auth/join', json={
            'token': invite_token,
            'username': 'short',
            'email': 'short@test.com',
            'password': '123',
        })
        assert resp.status_code == 400
        assert 'at least 8' in resp.get_json()['error'].lower()

    def test_join_missing_field(self, client):
        resp = client.post('/api/auth/join', json={
            'token': 'abc',
            'username': 'x',
            'password': 'SecurePass123!',
        })
        assert resp.status_code == 400
        assert 'email' in resp.get_json()['error'].lower()


# ---------------------------------------------------------------------------
# Member listing
# ---------------------------------------------------------------------------

class TestListMembers:

    def test_lists_all_members(self, client, admin_auth):
        admin_token, _, _ = admin_auth
        # Create invite and add a member
        create_resp = client.post(
            '/api/members/invite-links',
            json={},
            headers=auth_headers(admin_token),
        )
        invite_token = create_resp.get_json()['data']['token']
        client.post('/api/auth/join', json={
            'token': invite_token,
            'username': 'member2',
            'email': 'member2@test.com',
            'password': 'SecurePass123!',
        })

        resp = client.get('/api/members', headers=auth_headers(admin_token))
        assert resp.status_code == 200
        members = resp.get_json()['data']
        assert len(members) == 2  # admin + member


# ---------------------------------------------------------------------------
# Role management
# ---------------------------------------------------------------------------

class TestUpdateRole:

    def test_admin_changes_member_role(self, client, admin_auth):
        admin_token, _, _ = admin_auth
        # Create member
        create_resp = client.post(
            '/api/members/invite-links',
            json={'role': 'user'},
            headers=auth_headers(admin_token),
        )
        invite_token = create_resp.get_json()['data']['token']
        join_resp = client.post('/api/auth/join', json={
            'token': invite_token,
            'username': 'mem',
            'email': 'mem@test.com',
            'password': 'SecurePass123!',
        })
        member_id = join_resp.get_json()['user']['id']

        resp = client.put(
            f'/api/members/{member_id}/role',
            json={'role': 'admin'},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        assert resp.get_json()['data']['role'] == 'admin'

    def test_cannot_change_own_role(self, client, admin_auth):
        admin_token, _, admin_id = admin_auth
        resp = client.put(
            f'/api/members/{admin_id}/role',
            json={'role': 'user'},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 400
        assert 'own role' in resp.get_json()['error'].lower()


# ---------------------------------------------------------------------------
# Deactivation
# ---------------------------------------------------------------------------

class TestDeactivate:

    def test_deactivate_member(self, client, admin_auth):
        admin_token, _, _ = admin_auth
        create_resp = client.post(
            '/api/members/invite-links',
            json={},
            headers=auth_headers(admin_token),
        )
        invite_token = create_resp.get_json()['data']['token']
        join_resp = client.post('/api/auth/join', json={
            'token': invite_token,
            'username': 'target',
            'email': 'target@test.com',
            'password': 'SecurePass123!',
        })
        member_id = join_resp.get_json()['user']['id']

        resp = client.post(
            f'/api/members/{member_id}/deactivate',
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        assert resp.get_json()['data']['is_active'] is False

    def test_cannot_deactivate_self(self, client, admin_auth):
        admin_token, _, admin_id = admin_auth
        resp = client.post(
            f'/api/members/{admin_id}/deactivate',
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 400
        assert 'yourself' in resp.get_json()['error'].lower()


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:

    def test_invite_links_isolated(self, client, admin_auth):
        """Admin from Org A should not see invite links from Org B."""
        token_a, _, _ = admin_auth
        client.post('/api/members/invite-links', json={}, headers=auth_headers(token_a))

        # Register a second org
        resp_b = client.post('/api/auth/register', json={
            'org_name': 'Org B',
            'username': 'adminb',
            'email': 'adminb@orgb.com',
            'password': 'SecurePass123!',
        })
        token_b = resp_b.get_json()['access_token']

        resp = client.get('/api/members/invite-links', headers=auth_headers(token_b))
        assert resp.status_code == 200
        assert len(resp.get_json()['data']) == 0

    def test_members_isolated(self, client, admin_auth):
        """Admin from Org A should not see members from Org B."""
        token_a, _, _ = admin_auth

        resp_b = client.post('/api/auth/register', json={
            'org_name': 'Org B2',
            'username': 'adminb2',
            'email': 'adminb2@orgb.com',
            'password': 'SecurePass123!',
        })
        token_b = resp_b.get_json()['access_token']

        # Org A has 1 member (admin), Org B has 1 member (admin)
        resp_a = client.get('/api/members', headers=auth_headers(token_a))
        resp_b_members = client.get('/api/members', headers=auth_headers(token_b))

        # Each should only see their own members
        assert len(resp_a.get_json()['data']) == 1
        assert len(resp_b_members.get_json()['data']) == 1
        assert resp_a.get_json()['data'][0]['username'] == 'admin1'
        assert resp_b_members.get_json()['data'][0]['username'] == 'adminb2'
