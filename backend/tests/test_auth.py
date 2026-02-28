"""
Tests for the JWT authentication system.

Covers registration, login, token refresh, /me endpoint,
password hashing, input validation, and trial-expiration enforcement.
"""
import pytest
from datetime import datetime, timedelta, timezone

from app_factory import create_app
from database.models import Base, Organization, User
from database.session import engine, SessionLocal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def app():
    """Create a Flask test app and clean auth-related tables once per module."""
    app = create_app(testing=True)

    # Add a dummy protected POST endpoint so we can test trial-expiration
    # blocking on write operations through jwt_required.
    from middleware.auth import jwt_required

    @app.route('/api/test/protected-write', methods=['POST'])
    @jwt_required
    def _protected_write():
        return {'ok': True}, 200

    db = SessionLocal()
    try:
        db.query(User).delete()
        db.query(Organization).delete()
        db.commit()
    finally:
        db.close()

    yield app


@pytest.fixture(autouse=True)
def _clean_tables():
    """Ensure a clean slate before every test."""
    db = SessionLocal()
    try:
        db.query(User).delete()
        db.query(Organization).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def registered_user(client):
    """Register a standard user and return the JSON response body."""
    resp = client.post('/api/auth/register', json={
        'org_name': 'Test Org',
        'username': 'testuser',
        'email': 'test@example.com',
        'password': 'SecurePass123!',
    })
    return resp.get_json()


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------

class TestRegister:

    def test_creates_org_and_user(self, client):
        resp = client.post('/api/auth/register', json={
            'org_name': 'Test Org',
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'SecurePass123!',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert 'access_token' in data
        assert 'refresh_token' in data
        assert data['user']['role'] == 'admin'
        assert data['organization']['plan'] == 'trial'
        assert data['organization']['subscription_status'] == 'trialing'

    def test_duplicate_email_rejected(self, client, registered_user):
        resp = client.post('/api/auth/register', json={
            'org_name': 'Another Org',
            'username': 'another',
            'email': 'test@example.com',
            'password': 'SecurePass123!',
        })
        assert resp.status_code == 400
        assert 'already registered' in resp.get_json()['error'].lower()

    def test_short_password_rejected(self, client):
        resp = client.post('/api/auth/register', json={
            'org_name': 'Org',
            'username': 'user',
            'email': 'short@example.com',
            'password': '123',
        })
        assert resp.status_code == 400
        assert 'at least 8' in resp.get_json()['error'].lower()

    def test_missing_field_rejected(self, client):
        resp = client.post('/api/auth/register', json={
            'org_name': 'Org',
            'username': 'user',
            # email missing
            'password': 'SecurePass123!',
        })
        assert resp.status_code == 400
        assert 'email' in resp.get_json()['error'].lower()

    def test_empty_body_rejected(self, client):
        # Sending non-JSON content should be rejected (400 or 415)
        resp = client.post('/api/auth/register',
                           data='not json',
                           content_type='text/plain')
        assert resp.status_code in (400, 415)

    def test_null_json_body_rejected(self, client):
        # Sending Content-Type: application/json with null body
        resp = client.post('/api/auth/register',
                           data='null',
                           content_type='application/json')
        assert resp.status_code == 400

    def test_org_slug_generated(self, client):
        resp = client.post('/api/auth/register', json={
            'org_name': 'My Cool Org!',
            'username': 'admin',
            'email': 'admin@cool.org',
            'password': 'SecurePass123!',
        })
        data = resp.get_json()
        assert resp.status_code == 201
        assert data['organization']['slug'] == 'my-cool-org'

    def test_org_slug_deduplication(self, client):
        """Two orgs with the same name should get unique slugs."""
        client.post('/api/auth/register', json={
            'org_name': 'Dupe Org',
            'username': 'user1',
            'email': 'user1@dupe.org',
            'password': 'SecurePass123!',
        })
        resp2 = client.post('/api/auth/register', json={
            'org_name': 'Dupe Org',
            'username': 'user2',
            'email': 'user2@dupe.org',
            'password': 'SecurePass123!',
        })
        data2 = resp2.get_json()
        assert resp2.status_code == 201
        assert data2['organization']['slug'] == 'dupe-org-1'


# ---------------------------------------------------------------------------
# Login tests
# ---------------------------------------------------------------------------

class TestLogin:

    def test_login_returns_jwt(self, client, registered_user):
        resp = client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'SecurePass123!',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'access_token' in data
        assert 'refresh_token' in data

    def test_wrong_password(self, client, registered_user):
        resp = client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'WrongPassword',
        })
        assert resp.status_code == 401

    def test_nonexistent_email(self, client):
        resp = client.post('/api/auth/login', json={
            'email': 'nobody@example.com',
            'password': 'SomePassword123!',
        })
        assert resp.status_code == 401

    def test_missing_credentials(self, client):
        resp = client.post('/api/auth/login', json={})
        assert resp.status_code == 400

    def test_deactivated_user_rejected(self, client, registered_user):
        """A deactivated user should not be able to log in."""
        db = SessionLocal()
        try:
            user = db.query(User).filter_by(email='test@example.com').first()
            user.is_active = False
            db.commit()
        finally:
            db.close()

        resp = client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'SecurePass123!',
        })
        assert resp.status_code == 401
        assert 'deactivated' in resp.get_json()['error'].lower()


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

class TestPasswordHashing:

    def test_password_is_bcrypt(self, registered_user):
        db = SessionLocal()
        try:
            user = db.query(User).filter_by(email='test@example.com').first()
            assert user.password_hash.startswith('$2b$')
        finally:
            db.close()


# ---------------------------------------------------------------------------
# /me endpoint
# ---------------------------------------------------------------------------

class TestMe:

    def test_with_valid_token(self, client, registered_user):
        token = registered_user['access_token']
        resp = client.get(
            '/api/auth/me',
            headers={'Authorization': f'Bearer {token}'},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['user']['email'] == 'test@example.com'
        assert 'organization' in data

    def test_without_token(self, client):
        resp = client.get('/api/auth/me')
        assert resp.status_code == 401

    def test_with_invalid_token(self, client):
        resp = client.get(
            '/api/auth/me',
            headers={'Authorization': 'Bearer garbage.token.here'},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------

class TestRefresh:

    def test_refresh_returns_new_access_token(self, client, registered_user):
        resp = client.post('/api/auth/refresh', json={
            'refresh_token': registered_user['refresh_token'],
        })
        assert resp.status_code == 200
        assert 'access_token' in resp.get_json()

    def test_refresh_with_access_token_fails(self, client, registered_user):
        """Using an access token instead of a refresh token should fail."""
        resp = client.post('/api/auth/refresh', json={
            'refresh_token': registered_user['access_token'],
        })
        assert resp.status_code == 401

    def test_refresh_missing_token(self, client):
        resp = client.post('/api/auth/refresh', json={})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Trial expiration
# ---------------------------------------------------------------------------

class TestTrialExpiration:

    def _create_expired_org_user(self):
        """Helper: create an org with an expired trial and an admin user."""
        from services.user_service import hash_password
        db = SessionLocal()
        try:
            org = Organization(
                name='Expired Org',
                slug='expired-org',
                plan='trial',
                subscription_status='trialing',
                trial_ends_at=datetime.now(timezone.utc) - timedelta(days=1),
            )
            db.add(org)
            db.flush()

            user = User(
                tenant_id=org.id,
                username='expired',
                email='expired@example.com',
                password_hash=hash_password('SecurePass123!'),
                role='admin',
            )
            db.add(user)
            db.commit()
            return str(user.id), str(org.id)
        finally:
            db.close()

    def test_expired_trial_allows_read(self, client, app):
        """GET requests should still work after trial expiration."""
        self._create_expired_org_user()
        resp = client.post('/api/auth/login', json={
            'email': 'expired@example.com',
            'password': 'SecurePass123!',
        })
        token = resp.get_json()['access_token']

        resp = client.get(
            '/api/auth/me',
            headers={'Authorization': f'Bearer {token}'},
        )
        assert resp.status_code == 200

    def test_expired_trial_blocks_write(self, client, app):
        """POST requests on a protected endpoint should return 403."""
        self._create_expired_org_user()
        resp = client.post('/api/auth/login', json={
            'email': 'expired@example.com',
            'password': 'SecurePass123!',
        })
        token = resp.get_json()['access_token']

        resp = client.post(
            '/api/test/protected-write',
            headers={'Authorization': f'Bearer {token}'},
            json={'data': 'anything'},
        )
        assert resp.status_code == 403
        assert 'expired' in resp.get_json()['error'].lower()
