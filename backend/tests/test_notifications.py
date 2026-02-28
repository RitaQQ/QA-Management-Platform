"""
Tests for the notification alert system.

Covers email delivery, webhook delivery, health-check integration
(threshold + recovery), notification settings CRUD, and edge cases.
ALL external calls (SMTP, HTTP) are mocked — nothing leaves the process.
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock, call

from app_factory import create_app
from database.models import Organization, User, ApiEndpoint, ApiCheckHistory
from database.session import SessionLocal
from services.user_service import hash_password
from middleware.auth import create_access_token


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def app():
    """Create a Flask test application."""
    return create_app(testing=True)


@pytest.fixture(scope='module')
def tenant_data(app):
    """Create a tenant with notification settings and a JWT token."""
    db = SessionLocal()
    try:
        # Clean dependent tables first
        db.query(ApiCheckHistory).delete()
        db.query(ApiEndpoint).delete()
        db.query(User).delete()
        db.query(Organization).delete()
        db.commit()

        org = Organization(
            name='Notify Org',
            slug='notify-org',
            plan='trial',
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
            subscription_status='trialing',
            notification_email='alerts@example.com',
            notification_webhook_url='https://hooks.example.com/alert',
        )
        db.add(org)
        db.flush()

        user = User(
            tenant_id=org.id,
            username='notify_admin',
            email='admin@notify.com',
            password_hash=hash_password('Password123!'),
            role='admin',
        )
        db.add(user)
        db.flush()

        # Org without notification config
        org_no_notify = Organization(
            name='Silent Org',
            slug='silent-org',
            plan='trial',
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
            subscription_status='trialing',
            # notification_email and webhook intentionally left NULL
        )
        db.add(org_no_notify)
        db.flush()

        user_silent = User(
            tenant_id=org_no_notify.id,
            username='silent_user',
            email='user@silent.com',
            password_hash=hash_password('Password123!'),
            role='admin',
        )
        db.add(user_silent)
        db.flush()

        db.commit()

        token = create_access_token(str(user.id), str(org.id), 'admin')
        token_silent = create_access_token(
            str(user_silent.id), str(org_no_notify.id), 'admin',
        )

        yield {
            'org_id': str(org.id),
            'token': token,
            'org_silent_id': str(org_no_notify.id),
            'token_silent': token_silent,
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
    return app.test_client()


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


def _create_endpoint(client, token, **overrides):
    """Helper — create an API endpoint via the REST API."""
    payload = {
        'name': 'Notify Test API',
        'url': 'https://api.example.com/health',
        'method': 'GET',
    }
    payload.update(overrides)
    resp = client.post('/api/endpoints', json=payload, headers=_auth(token))
    return resp


def _mock_unhealthy_response():
    """Return a MagicMock that looks like an HTTP 500 response."""
    mock = MagicMock()
    mock.status_code = 500
    mock.text = 'Internal Server Error'
    return mock


def _mock_healthy_response():
    """Return a MagicMock that looks like an HTTP 200 response."""
    mock = MagicMock()
    mock.status_code = 200
    mock.text = 'ok'
    return mock


# ---------------------------------------------------------------------------
# 1. Email sent when API becomes unhealthy
# ---------------------------------------------------------------------------

class TestEmailOnUnhealthy:

    @patch('services.notification_service.send_email')
    @patch('services.notification_service.send_webhook')
    @patch('services.api_monitor_service.http_requests.request')
    def test_send_email_called_on_unhealthy(
        self, mock_http, mock_webhook, mock_email, client, tenant_data,
    ):
        """Email should be sent when error_count reaches threshold (3)."""
        mock_http.return_value = _mock_unhealthy_response()
        mock_email.return_value = True
        mock_webhook.return_value = True

        create_resp = _create_endpoint(client, tenant_data['token'])
        ep_id = create_resp.get_json()['data']['id']

        # Trigger 3 consecutive failures (threshold = 3)
        for _ in range(3):
            client.post(
                f'/api/endpoints/{ep_id}/check',
                headers=_auth(tenant_data['token']),
            )

        # Email should have been called exactly once (at error_count == 3)
        assert mock_email.called
        call_args = mock_email.call_args
        assert call_args[0][0] == 'alerts@example.com'  # to_email
        assert 'unhealthy' in call_args[0][1].lower()    # subject


# ---------------------------------------------------------------------------
# 2. Webhook sent when API becomes unhealthy
# ---------------------------------------------------------------------------

class TestWebhookOnUnhealthy:

    @patch('services.notification_service.send_email')
    @patch('services.notification_service.send_webhook')
    @patch('services.api_monitor_service.http_requests.request')
    def test_send_webhook_called_on_unhealthy(
        self, mock_http, mock_webhook, mock_email, client, tenant_data,
    ):
        """Webhook should be called when error_count reaches threshold."""
        mock_http.return_value = _mock_unhealthy_response()
        mock_email.return_value = True
        mock_webhook.return_value = True

        create_resp = _create_endpoint(client, tenant_data['token'])
        ep_id = create_resp.get_json()['data']['id']

        for _ in range(3):
            client.post(
                f'/api/endpoints/{ep_id}/check',
                headers=_auth(tenant_data['token']),
            )

        assert mock_webhook.called
        call_args = mock_webhook.call_args
        assert call_args[0][0] == 'https://hooks.example.com/alert'
        payload = call_args[0][1]
        assert payload['event'] == 'api_unhealthy'
        assert payload['status'] == 'unhealthy'


# ---------------------------------------------------------------------------
# 3. Notification on recovery
# ---------------------------------------------------------------------------

class TestNotificationOnRecovery:

    @patch('services.notification_service.send_email')
    @patch('services.notification_service.send_webhook')
    @patch('services.api_monitor_service.http_requests.request')
    def test_notification_on_recovery(
        self, mock_http, mock_webhook, mock_email, client, tenant_data,
    ):
        """Notifications should fire when an endpoint recovers."""
        mock_email.return_value = True
        mock_webhook.return_value = True

        create_resp = _create_endpoint(client, tenant_data['token'])
        ep_id = create_resp.get_json()['data']['id']

        # Make endpoint unhealthy first (need to reach threshold first)
        mock_http.return_value = _mock_unhealthy_response()
        for _ in range(3):
            client.post(
                f'/api/endpoints/{ep_id}/check',
                headers=_auth(tenant_data['token']),
            )

        # Reset mocks to track recovery notifications separately
        mock_email.reset_mock()
        mock_webhook.reset_mock()

        # Now recover
        mock_http.return_value = _mock_healthy_response()
        client.post(
            f'/api/endpoints/{ep_id}/check',
            headers=_auth(tenant_data['token']),
        )

        # Recovery notifications should fire
        assert mock_email.called
        subject = mock_email.call_args[0][1]
        assert 'recovered' in subject.lower()

        assert mock_webhook.called
        payload = mock_webhook.call_args[0][1]
        assert payload['event'] == 'api_recovered'
        assert payload['status'] == 'healthy'


# ---------------------------------------------------------------------------
# 4. No notification below threshold
# ---------------------------------------------------------------------------

class TestNoBelowThreshold:

    @patch('services.notification_service.send_email')
    @patch('services.notification_service.send_webhook')
    @patch('services.api_monitor_service.http_requests.request')
    def test_no_notification_below_threshold(
        self, mock_http, mock_webhook, mock_email, client, tenant_data,
    ):
        """No notification should fire when error_count < threshold (3)."""
        mock_http.return_value = _mock_unhealthy_response()

        create_resp = _create_endpoint(client, tenant_data['token'])
        ep_id = create_resp.get_json()['data']['id']

        # Only 2 failures — below threshold
        for _ in range(2):
            client.post(
                f'/api/endpoints/{ep_id}/check',
                headers=_auth(tenant_data['token']),
            )

        # No notifications should have been sent
        assert not mock_email.called
        assert not mock_webhook.called


# ---------------------------------------------------------------------------
# 5. Webhook payload format
# ---------------------------------------------------------------------------

class TestWebhookPayloadFormat:

    @patch('services.notification_service.send_email')
    @patch('services.notification_service.send_webhook')
    @patch('services.api_monitor_service.http_requests.request')
    def test_webhook_payload_format(
        self, mock_http, mock_webhook, mock_email, client, tenant_data,
    ):
        """Webhook payload should contain all required fields."""
        mock_http.return_value = _mock_unhealthy_response()
        mock_email.return_value = True
        mock_webhook.return_value = True

        create_resp = _create_endpoint(client, tenant_data['token'])
        ep_id = create_resp.get_json()['data']['id']

        for _ in range(3):
            client.post(
                f'/api/endpoints/{ep_id}/check',
                headers=_auth(tenant_data['token']),
            )

        payload = mock_webhook.call_args[0][1]
        required_fields = {
            'event', 'api_name', 'api_url', 'status',
            'error_count', 'error', 'organization',
        }
        assert required_fields.issubset(set(payload.keys()))
        assert payload['api_name'] == 'Notify Test API'
        assert payload['api_url'] == 'https://api.example.com/health'
        assert payload['organization'] == 'Notify Org'
        assert payload['error_count'] == 3


# ---------------------------------------------------------------------------
# 6. Email not sent if not configured
# ---------------------------------------------------------------------------

class TestEmailNotSentIfNotConfigured:

    @patch('services.notification_service.send_email')
    @patch('services.notification_service.send_webhook')
    @patch('services.api_monitor_service.http_requests.request')
    def test_email_not_sent_if_not_configured(
        self, mock_http, mock_webhook, mock_email, client, tenant_data,
    ):
        """No crash and no email call when org has no notification email."""
        mock_http.return_value = _mock_unhealthy_response()

        create_resp = _create_endpoint(client, tenant_data['token_silent'])
        ep_id = create_resp.get_json()['data']['id']

        for _ in range(3):
            client.post(
                f'/api/endpoints/{ep_id}/check',
                headers=_auth(tenant_data['token_silent']),
            )

        # Neither email nor webhook should be called (both unconfigured)
        assert not mock_email.called
        assert not mock_webhook.called


# ---------------------------------------------------------------------------
# 7. GET notification settings
# ---------------------------------------------------------------------------

class TestGetNotificationSettings:

    def test_get_notification_settings(self, client, tenant_data):
        """Should return current notification email and webhook URL."""
        resp = client.get(
            '/api/notifications/settings',
            headers=_auth(tenant_data['token']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['notification_email'] == 'alerts@example.com'
        assert data['notification_webhook_url'] == 'https://hooks.example.com/alert'

    def test_get_notification_settings_empty(self, client, tenant_data):
        """Org without notification config should return null values."""
        resp = client.get(
            '/api/notifications/settings',
            headers=_auth(tenant_data['token_silent']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['notification_email'] is None
        assert data['notification_webhook_url'] is None


# ---------------------------------------------------------------------------
# 8. PUT notification settings
# ---------------------------------------------------------------------------

class TestUpdateNotificationSettings:

    def test_update_notification_settings(self, client, tenant_data):
        """Should update email and webhook URL."""
        resp = client.put(
            '/api/notifications/settings',
            json={
                'notification_email': 'new-alerts@example.com',
                'notification_webhook_url': 'https://hooks.example.com/new',
            },
            headers=_auth(tenant_data['token']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['notification_email'] == 'new-alerts@example.com'
        assert data['notification_webhook_url'] == 'https://hooks.example.com/new'

        # Verify persistence via GET
        resp2 = client.get(
            '/api/notifications/settings',
            headers=_auth(tenant_data['token']),
        )
        data2 = resp2.get_json()['data']
        assert data2['notification_email'] == 'new-alerts@example.com'

        # Restore original values for other tests
        client.put(
            '/api/notifications/settings',
            json={
                'notification_email': 'alerts@example.com',
                'notification_webhook_url': 'https://hooks.example.com/alert',
            },
            headers=_auth(tenant_data['token']),
        )

    def test_update_partial_settings(self, client, tenant_data):
        """Should allow updating only one field."""
        resp = client.put(
            '/api/notifications/settings',
            json={'notification_email': 'partial@example.com'},
            headers=_auth(tenant_data['token']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['notification_email'] == 'partial@example.com'
        # Webhook should remain unchanged
        assert data['notification_webhook_url'] == 'https://hooks.example.com/alert'

        # Restore
        client.put(
            '/api/notifications/settings',
            json={'notification_email': 'alerts@example.com'},
            headers=_auth(tenant_data['token']),
        )

    def test_update_requires_body(self, client, tenant_data):
        """PUT without body should return 400."""
        resp = client.put(
            '/api/notifications/settings',
            headers=_auth(tenant_data['token']),
            content_type='application/json',
        )
        assert resp.status_code == 400
