"""
Tests for the API monitoring module.

Covers endpoint CRUD, health checks with mocked HTTP, history retrieval,
uptime calculation, tenant isolation, and status updates after checks.
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

from app_factory import create_app
from database.models import (
    Organization, User, ApiEndpoint, ApiCheckHistory,
)
from database.session import SessionLocal
from services.user_service import hash_password
from middleware.auth import create_access_token


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def app():
    """Create a Flask test application."""
    application = create_app(testing=True)
    yield application


@pytest.fixture(scope='module')
def tenant_data(app):
    """Create two tenants with users and tokens for isolation tests.

    Yields a dict containing org IDs, user IDs, and JWT tokens for both
    Tenant A and Tenant B.
    """
    db = SessionLocal()
    try:
        # Clean tables in dependency order
        db.query(ApiCheckHistory).delete()
        db.query(ApiEndpoint).delete()
        db.query(User).delete()
        db.query(Organization).delete()
        db.commit()

        # -- Tenant A ---------------------------------------------------------
        org_a = Organization(
            name='Monitor Org A',
            slug='monitor-org-a',
            plan='trial',
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
            subscription_status='trialing',
        )
        db.add(org_a)
        db.flush()

        user_a = User(
            tenant_id=org_a.id,
            username='monitor_a',
            email='monitor_a@test.com',
            password_hash=hash_password('Password123!'),
            role='admin',
        )
        db.add(user_a)
        db.flush()

        # -- Tenant B ---------------------------------------------------------
        org_b = Organization(
            name='Monitor Org B',
            slug='monitor-org-b',
            plan='trial',
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
            subscription_status='trialing',
        )
        db.add(org_b)
        db.flush()

        user_b = User(
            tenant_id=org_b.id,
            username='monitor_b',
            email='monitor_b@test.com',
            password_hash=hash_password('Password123!'),
            role='admin',
        )
        db.add(user_b)
        db.flush()

        db.commit()

        token_a = create_access_token(str(user_a.id), str(org_a.id), 'admin')
        token_b = create_access_token(str(user_b.id), str(org_b.id), 'admin')

        yield {
            'org_a_id': str(org_a.id),
            'org_b_id': str(org_b.id),
            'token_a': token_a,
            'token_b': token_b,
        }
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _clean_endpoints():
    """Remove all endpoints and history before each test."""
    db = SessionLocal()
    try:
        db.query(ApiCheckHistory).delete()
        db.query(ApiEndpoint).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture
def client(app):
    """Return a Flask test client."""
    return app.test_client()


def _auth(token):
    """Build an Authorization header dict."""
    return {'Authorization': f'Bearer {token}'}


def _create_endpoint(client, token, **overrides):
    """Helper — create an endpoint via the API and return the response JSON."""
    payload = {
        'name': 'Test API',
        'url': 'https://api.example.com/health',
        'method': 'GET',
    }
    payload.update(overrides)
    resp = client.post(
        '/api/endpoints',
        json=payload,
        headers=_auth(token),
    )
    return resp


# ---------------------------------------------------------------------------
# 1. Create endpoint
# ---------------------------------------------------------------------------

class TestCreateEndpoint:

    def test_create_endpoint_returns_201(self, client, tenant_data):
        resp = _create_endpoint(client, tenant_data['token_a'])
        assert resp.status_code == 201
        data = resp.get_json()['data']
        assert data['name'] == 'Test API'
        assert data['url'] == 'https://api.example.com/health'
        assert data['method'] == 'GET'
        assert data['status'] == 'unknown'
        assert data['is_active'] is True
        assert 'id' in data

    def test_create_endpoint_missing_name(self, client, tenant_data):
        resp = client.post(
            '/api/endpoints',
            json={'url': 'https://example.com'},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 400
        assert 'name' in resp.get_json()['error'].lower()

    def test_create_endpoint_missing_url(self, client, tenant_data):
        resp = client.post(
            '/api/endpoints',
            json={'name': 'No URL'},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 400
        assert 'url' in resp.get_json()['error'].lower()

    def test_create_endpoint_invalid_url(self, client, tenant_data):
        resp = client.post(
            '/api/endpoints',
            json={'name': 'Bad URL', 'url': 'ftp://bad.example.com'},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 400

    def test_create_endpoint_invalid_method(self, client, tenant_data):
        resp = client.post(
            '/api/endpoints',
            json={'name': 'Bad Method', 'url': 'https://example.com', 'method': 'INVALID'},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 2. List endpoints
# ---------------------------------------------------------------------------

class TestListEndpoints:

    def test_list_returns_only_current_tenant(self, client, tenant_data):
        # Create an endpoint for Tenant A
        _create_endpoint(client, tenant_data['token_a'], name='Tenant A Endpoint')

        # Create an endpoint for Tenant B
        _create_endpoint(client, tenant_data['token_b'], name='Tenant B Endpoint')

        # List as Tenant A — should only see Tenant A's endpoint
        resp = client.get('/api/endpoints', headers=_auth(tenant_data['token_a']))
        assert resp.status_code == 200
        names = [ep['name'] for ep in resp.get_json()['data']]
        assert 'Tenant A Endpoint' in names
        assert 'Tenant B Endpoint' not in names

    def test_list_empty(self, client, tenant_data):
        resp = client.get('/api/endpoints', headers=_auth(tenant_data['token_a']))
        assert resp.status_code == 200
        assert resp.get_json()['data'] == []


# ---------------------------------------------------------------------------
# 3. Get single endpoint
# ---------------------------------------------------------------------------

class TestGetEndpoint:

    def test_get_endpoint_by_id(self, client, tenant_data):
        create_resp = _create_endpoint(client, tenant_data['token_a'])
        ep_id = create_resp.get_json()['data']['id']

        resp = client.get(f'/api/endpoints/{ep_id}', headers=_auth(tenant_data['token_a']))
        assert resp.status_code == 200
        assert resp.get_json()['data']['id'] == ep_id

    def test_get_nonexistent_endpoint(self, client, tenant_data):
        resp = client.get('/api/endpoints/99999', headers=_auth(tenant_data['token_a']))
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 4. Update endpoint
# ---------------------------------------------------------------------------

class TestUpdateEndpoint:

    def test_update_endpoint_fields(self, client, tenant_data):
        create_resp = _create_endpoint(client, tenant_data['token_a'])
        ep_id = create_resp.get_json()['data']['id']

        resp = client.put(
            f'/api/endpoints/{ep_id}',
            json={'name': 'Updated API', 'method': 'POST'},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['name'] == 'Updated API'
        assert data['method'] == 'POST'

    def test_update_nonexistent_endpoint(self, client, tenant_data):
        resp = client.put(
            '/api/endpoints/99999',
            json={'name': 'Ghost'},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 5. Delete endpoint
# ---------------------------------------------------------------------------

class TestDeleteEndpoint:

    def test_delete_endpoint_returns_200(self, client, tenant_data):
        create_resp = _create_endpoint(client, tenant_data['token_a'])
        ep_id = create_resp.get_json()['data']['id']

        resp = client.delete(f'/api/endpoints/{ep_id}', headers=_auth(tenant_data['token_a']))
        assert resp.status_code == 200

        # Verify it is gone
        resp = client.get(f'/api/endpoints/{ep_id}', headers=_auth(tenant_data['token_a']))
        assert resp.status_code == 404

    def test_delete_nonexistent_endpoint(self, client, tenant_data):
        resp = client.delete('/api/endpoints/99999', headers=_auth(tenant_data['token_a']))
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 6. Health check saves history
# ---------------------------------------------------------------------------

class TestCheckEndpoint:

    @patch('services.api_monitor_service.http_requests.request')
    def test_check_endpoint_saves_history(self, mock_request, client, tenant_data):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.elapsed.total_seconds.return_value = 0.15
        mock_response.text = '{"status": "ok"}'
        mock_request.return_value = mock_response

        create_resp = _create_endpoint(client, tenant_data['token_a'])
        ep_id = create_resp.get_json()['data']['id']

        # Trigger health check
        resp = client.post(
            f'/api/endpoints/{ep_id}/check',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        check_data = resp.get_json()['data']
        assert check_data['check']['status'] == 'healthy'

        # Verify history was saved
        history_resp = client.get(
            f'/api/endpoints/{ep_id}/history?days=1',
            headers=_auth(tenant_data['token_a']),
        )
        assert history_resp.status_code == 200
        history = history_resp.get_json()['data']
        assert len(history) > 0
        assert history[0]['status'] == 'healthy'
        assert history[0]['status_code'] == 200

    @patch('services.api_monitor_service.http_requests.request')
    def test_check_nonexistent_endpoint(self, mock_request, client, tenant_data):
        resp = client.post(
            '/api/endpoints/99999/check',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 7. History retrieval
# ---------------------------------------------------------------------------

class TestGetHistory:

    @patch('services.api_monitor_service.http_requests.request')
    def test_get_history_returns_recent_data(self, mock_request, client, tenant_data):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = 'ok'
        mock_request.return_value = mock_response

        create_resp = _create_endpoint(client, tenant_data['token_a'])
        ep_id = create_resp.get_json()['data']['id']

        # Trigger two checks
        client.post(f'/api/endpoints/{ep_id}/check', headers=_auth(tenant_data['token_a']))
        client.post(f'/api/endpoints/{ep_id}/check', headers=_auth(tenant_data['token_a']))

        resp = client.get(
            f'/api/endpoints/{ep_id}/history?days=1',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert len(data) == 2

    def test_get_history_nonexistent_endpoint(self, client, tenant_data):
        resp = client.get(
            '/api/endpoints/99999/history',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 8. Uptime calculation
# ---------------------------------------------------------------------------

class TestUptimeCalculation:

    def test_uptime_calculation_is_correct(self, client, tenant_data):
        """Directly insert history records and verify uptime math."""
        # Create endpoint first via API
        create_resp = _create_endpoint(client, tenant_data['token_a'])
        ep_id = create_resp.get_json()['data']['id']

        # Insert history records directly
        db = SessionLocal()
        try:
            endpoint = db.query(ApiEndpoint).filter_by(id=ep_id).first()
            now = datetime.now(timezone.utc)

            # 7 healthy, 3 unhealthy = 70% uptime
            for i in range(7):
                db.add(ApiCheckHistory(
                    api_id=ep_id,
                    tenant_id=endpoint.tenant_id,
                    status='healthy',
                    status_code=200,
                    response_time_ms=100 + i,
                    checked_at=now - timedelta(hours=i),
                ))
            for i in range(3):
                db.add(ApiCheckHistory(
                    api_id=ep_id,
                    tenant_id=endpoint.tenant_id,
                    status='unhealthy',
                    status_code=500,
                    response_time_ms=200,
                    checked_at=now - timedelta(hours=7 + i),
                ))
            db.commit()
        finally:
            db.close()

        resp = client.get(
            f'/api/endpoints/{ep_id}/uptime?days=7',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['total_checks'] == 10
        assert data['healthy_checks'] == 7
        assert data['uptime_percent'] == 70.0
        assert data['period_days'] == 7

    def test_uptime_no_history(self, client, tenant_data):
        """Uptime with no history should return 0%."""
        create_resp = _create_endpoint(client, tenant_data['token_a'])
        ep_id = create_resp.get_json()['data']['id']

        resp = client.get(
            f'/api/endpoints/{ep_id}/uptime?days=7',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['uptime_percent'] == 0
        assert data['total_checks'] == 0


# ---------------------------------------------------------------------------
# 9. Tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:

    def test_tenant_a_cannot_see_tenant_b_endpoints(self, client, tenant_data):
        """Tenant A should not see Tenant B's endpoints."""
        _create_endpoint(client, tenant_data['token_a'], name='A Only')
        _create_endpoint(client, tenant_data['token_b'], name='B Only')

        # List as Tenant A
        resp_a = client.get('/api/endpoints', headers=_auth(tenant_data['token_a']))
        names_a = [ep['name'] for ep in resp_a.get_json()['data']]
        assert 'A Only' in names_a
        assert 'B Only' not in names_a

        # List as Tenant B
        resp_b = client.get('/api/endpoints', headers=_auth(tenant_data['token_b']))
        names_b = [ep['name'] for ep in resp_b.get_json()['data']]
        assert 'B Only' in names_b
        assert 'A Only' not in names_b

    def test_tenant_a_cannot_get_tenant_b_endpoint(self, client, tenant_data):
        """Tenant A requesting Tenant B's endpoint by ID should get 404."""
        create_resp = _create_endpoint(client, tenant_data['token_b'], name='Secret B')
        ep_id = create_resp.get_json()['data']['id']

        resp = client.get(
            f'/api/endpoints/{ep_id}',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404

    def test_tenant_a_cannot_delete_tenant_b_endpoint(self, client, tenant_data):
        """DELETE across tenants should return 404."""
        create_resp = _create_endpoint(client, tenant_data['token_b'], name='B Protected')
        ep_id = create_resp.get_json()['data']['id']

        resp = client.delete(
            f'/api/endpoints/{ep_id}',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404

    def test_tenant_a_cannot_update_tenant_b_endpoint(self, client, tenant_data):
        """PUT across tenants should return 404."""
        create_resp = _create_endpoint(client, tenant_data['token_b'], name='B Edit')
        ep_id = create_resp.get_json()['data']['id']

        resp = client.put(
            f'/api/endpoints/{ep_id}',
            json={'name': 'Hacked!'},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 10. Check updates endpoint status
# ---------------------------------------------------------------------------

class TestCheckUpdatesStatus:

    @patch('services.api_monitor_service.http_requests.request')
    def test_check_endpoint_updates_status_to_healthy(self, mock_request, client, tenant_data):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = 'ok'
        mock_request.return_value = mock_response

        create_resp = _create_endpoint(client, tenant_data['token_a'])
        ep_id = create_resp.get_json()['data']['id']

        # Initial status should be 'unknown'
        resp = client.get(f'/api/endpoints/{ep_id}', headers=_auth(tenant_data['token_a']))
        assert resp.get_json()['data']['status'] == 'unknown'

        # Trigger health check
        client.post(f'/api/endpoints/{ep_id}/check', headers=_auth(tenant_data['token_a']))

        # Status should now be 'healthy'
        resp = client.get(f'/api/endpoints/{ep_id}', headers=_auth(tenant_data['token_a']))
        assert resp.get_json()['data']['status'] == 'healthy'
        assert resp.get_json()['data']['error_count'] == 0

    @patch('services.api_monitor_service.http_requests.request')
    def test_check_endpoint_updates_status_to_unhealthy(self, mock_request, client, tenant_data):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = 'Internal Server Error'
        mock_request.return_value = mock_response

        create_resp = _create_endpoint(client, tenant_data['token_a'])
        ep_id = create_resp.get_json()['data']['id']

        # Trigger health check
        client.post(f'/api/endpoints/{ep_id}/check', headers=_auth(tenant_data['token_a']))

        # Status should now be 'unhealthy'
        resp = client.get(f'/api/endpoints/{ep_id}', headers=_auth(tenant_data['token_a']))
        data = resp.get_json()['data']
        assert data['status'] == 'unhealthy'
        assert data['error_count'] == 1

    @patch('services.api_monitor_service.http_requests.request')
    def test_error_count_increments(self, mock_request, client, tenant_data):
        """Consecutive failures should increment error_count."""
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.text = 'Service Unavailable'
        mock_request.return_value = mock_response

        create_resp = _create_endpoint(client, tenant_data['token_a'])
        ep_id = create_resp.get_json()['data']['id']

        # Two consecutive failures
        client.post(f'/api/endpoints/{ep_id}/check', headers=_auth(tenant_data['token_a']))
        client.post(f'/api/endpoints/{ep_id}/check', headers=_auth(tenant_data['token_a']))

        resp = client.get(f'/api/endpoints/{ep_id}', headers=_auth(tenant_data['token_a']))
        assert resp.get_json()['data']['error_count'] == 2

    @patch('services.api_monitor_service.http_requests.request')
    def test_error_count_resets_on_healthy(self, mock_request, client, tenant_data):
        """A successful check should reset error_count to 0."""
        # First: unhealthy
        mock_response_bad = MagicMock()
        mock_response_bad.status_code = 500
        mock_response_bad.text = 'Error'
        mock_request.return_value = mock_response_bad

        create_resp = _create_endpoint(client, tenant_data['token_a'])
        ep_id = create_resp.get_json()['data']['id']

        client.post(f'/api/endpoints/{ep_id}/check', headers=_auth(tenant_data['token_a']))

        resp = client.get(f'/api/endpoints/{ep_id}', headers=_auth(tenant_data['token_a']))
        assert resp.get_json()['data']['error_count'] == 1

        # Then: healthy
        mock_response_ok = MagicMock()
        mock_response_ok.status_code = 200
        mock_response_ok.text = 'ok'
        mock_request.return_value = mock_response_ok

        client.post(f'/api/endpoints/{ep_id}/check', headers=_auth(tenant_data['token_a']))

        resp = client.get(f'/api/endpoints/{ep_id}', headers=_auth(tenant_data['token_a']))
        assert resp.get_json()['data']['error_count'] == 0

    @patch('services.api_monitor_service.http_requests.request')
    def test_timeout_handled_gracefully(self, mock_request, client, tenant_data):
        """A timeout should result in 'unhealthy' without server error."""
        import requests as real_requests
        mock_request.side_effect = real_requests.exceptions.Timeout('Connection timed out')

        create_resp = _create_endpoint(client, tenant_data['token_a'])
        ep_id = create_resp.get_json()['data']['id']

        resp = client.post(
            f'/api/endpoints/{ep_id}/check',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        check = resp.get_json()['data']['check']
        assert check['status'] == 'unhealthy'
        assert 'timeout' in check['error_message'].lower()
