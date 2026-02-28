"""
Tests for the Jira integration module.

Covers API Token connection, test connection, disconnect, issue creation
from test results, webhook handling, manual sync, project link querying,
connection status, and tenant isolation.

ALL external Jira HTTP calls are mocked -- no real Jira access is required.
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

from app_factory import create_app
from database.models import (
    Organization, User, TestCase, TestProject, TestResult,
    JiraIssueLink, ApiEndpoint, ApiTestcaseLink, ApiCheckHistory,
    TestCaseTag, ProductTag,
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
    """Create two tenants with users, projects, test cases, and test results.

    Yields a dict containing IDs and JWT tokens for both tenants.
    """
    db = SessionLocal()
    try:
        # Clean all tables in dependency order
        db.query(JiraIssueLink).delete()
        db.query(ApiTestcaseLink).delete()
        db.query(TestResult).delete()
        db.query(TestCaseTag).delete()
        db.query(TestCase).delete()
        db.query(TestProject).delete()
        db.query(ProductTag).delete()
        db.query(ApiCheckHistory).delete()
        db.query(ApiEndpoint).delete()
        db.query(User).delete()
        db.query(Organization).delete()
        db.commit()

        # -- Tenant A ---------------------------------------------------------
        org_a = Organization(
            name='Jira Org A',
            slug='jira-org-a',
            plan='trial',
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
            subscription_status='trialing',
            jira_site_url='https://orgA.atlassian.net',
            jira_user_email='admin@orgA.com',
            jira_api_token='fake-api-token-a',
        )
        db.add(org_a)
        db.flush()

        user_a = User(
            tenant_id=org_a.id,
            username='jira_user_a',
            email='jira_a@test.com',
            password_hash=hash_password('Password123!'),
            role='admin',
        )
        db.add(user_a)
        db.flush()

        project_a = TestProject(
            tenant_id=org_a.id,
            name='Jira Project A',
            description='Test project A',
            status='in_progress',
        )
        db.add(project_a)
        db.flush()

        case_a = TestCase(
            tenant_id=org_a.id,
            tc_id='TC00001',
            title='Login Feature Test',
            user_role='Admin',
            feature_description='User login with OAuth',
            acceptance_criteria='User can log in and see dashboard',
            priority='high',
            status='ready',
        )
        db.add(case_a)
        db.flush()

        result_a = TestResult(
            tenant_id=org_a.id,
            project_id=project_a.id,
            test_case_id=case_a.id,
            status='fail',
            notes='Login button not working',
            known_issues='Button CSS broken',
        )
        db.add(result_a)
        db.flush()

        # -- Tenant B ---------------------------------------------------------
        org_b = Organization(
            name='Jira Org B',
            slug='jira-org-b',
            plan='trial',
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
            subscription_status='trialing',
            jira_site_url='https://orgB.atlassian.net',
            jira_user_email='admin@orgB.com',
            jira_api_token='fake-api-token-b',
        )
        db.add(org_b)
        db.flush()

        user_b = User(
            tenant_id=org_b.id,
            username='jira_user_b',
            email='jira_b@test.com',
            password_hash=hash_password('Password123!'),
            role='admin',
        )
        db.add(user_b)
        db.flush()

        project_b = TestProject(
            tenant_id=org_b.id,
            name='Jira Project B',
            description='Test project B',
            status='in_progress',
        )
        db.add(project_b)
        db.flush()

        case_b = TestCase(
            tenant_id=org_b.id,
            tc_id='TC00001',
            title='Signup Feature Test',
            priority='medium',
            status='ready',
        )
        db.add(case_b)
        db.flush()

        result_b = TestResult(
            tenant_id=org_b.id,
            project_id=project_b.id,
            test_case_id=case_b.id,
            status='fail',
            notes='Signup timeout',
        )
        db.add(result_b)
        db.flush()

        db.commit()

        token_a = create_access_token(str(user_a.id), str(org_a.id), 'admin')
        token_b = create_access_token(str(user_b.id), str(org_b.id), 'admin')

        yield {
            'org_a_id': str(org_a.id),
            'org_b_id': str(org_b.id),
            'user_a_id': str(user_a.id),
            'user_b_id': str(user_b.id),
            'token_a': token_a,
            'token_b': token_b,
            'project_a_id': project_a.id,
            'project_b_id': project_b.id,
            'case_a_id': case_a.id,
            'case_b_id': case_b.id,
            'result_a_id': result_a.id,
            'result_b_id': result_b.id,
        }
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _clean_jira_links():
    """Remove all Jira issue links before each test."""
    db = SessionLocal()
    try:
        db.query(JiraIssueLink).delete()
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


# ---------------------------------------------------------------------------
# 1. test_connect_with_token -- Stores credentials
# ---------------------------------------------------------------------------

class TestConnectWithToken:

    def test_connect_saves_credentials(self, client, tenant_data):
        """POST /api/jira/connect saves site_url, email, and api_token."""
        resp = client.post(
            '/api/jira/connect',
            json={
                'site_url': 'https://new-site.atlassian.net',
                'email': 'new@example.com',
                'api_token': 'new-token-123',
            },
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['connected'] is True
        assert data['site_url'] == 'https://new-site.atlassian.net'
        assert data['user_email'] == 'new@example.com'

        # Verify saved in DB
        db = SessionLocal()
        try:
            org = db.query(Organization).filter_by(id=tenant_data['org_a_id']).first()
            assert org.jira_site_url == 'https://new-site.atlassian.net'
            assert org.jira_user_email == 'new@example.com'
            assert org.jira_api_token == 'new-token-123'
            # OAuth fields should be cleared
            assert org.jira_access_token is None
            assert org.jira_cloud_id is None
        finally:
            # Restore original credentials for other tests
            org.jira_site_url = 'https://orgA.atlassian.net'
            org.jira_user_email = 'admin@orgA.com'
            org.jira_api_token = 'fake-api-token-a'
            db.commit()
            db.close()

    def test_connect_missing_fields(self, client, tenant_data):
        """POST /api/jira/connect without required fields returns 400."""
        resp = client.post(
            '/api/jira/connect',
            json={'site_url': 'https://example.atlassian.net'},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 400
        assert 'required' in resp.get_json()['error'].lower()

    def test_connect_normalises_url(self, client, tenant_data):
        """POST /api/jira/connect normalises site URL (adds https, strips trailing slash)."""
        resp = client.post(
            '/api/jira/connect',
            json={
                'site_url': 'my-org.atlassian.net/',
                'email': 'u@test.com',
                'api_token': 'tok',
            },
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['site_url'] == 'https://my-org.atlassian.net'

        # Restore
        db = SessionLocal()
        try:
            org = db.query(Organization).filter_by(id=tenant_data['org_a_id']).first()
            org.jira_site_url = 'https://orgA.atlassian.net'
            org.jira_user_email = 'admin@orgA.com'
            org.jira_api_token = 'fake-api-token-a'
            db.commit()
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 2. test_test_connection -- Validates stored credentials
# ---------------------------------------------------------------------------

class TestTestConnection:

    @patch('services.jira_service.requests.get')
    def test_connection_success(self, mock_get, client, tenant_data):
        """POST /api/jira/test-connection returns ok when credentials valid."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {'displayName': 'Test User', 'emailAddress': 'admin@orgA.com'},
        )

        resp = client.post('/api/jira/test-connection', headers=_auth(tenant_data['token_a']))
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['ok'] is True
        assert data['display_name'] == 'Test User'

    @patch('services.jira_service.requests.get')
    def test_connection_invalid_credentials(self, mock_get, client, tenant_data):
        """POST /api/jira/test-connection returns error for invalid credentials."""
        mock_get.return_value = MagicMock(status_code=401)

        resp = client.post('/api/jira/test-connection', headers=_auth(tenant_data['token_a']))
        assert resp.status_code == 400
        assert 'Invalid credentials' in resp.get_json()['error']

    @patch('services.jira_service.requests.get')
    def test_connection_network_error(self, mock_get, client, tenant_data):
        """POST /api/jira/test-connection returns error on network failure."""
        import requests as real_requests
        mock_get.side_effect = real_requests.ConnectionError('DNS lookup failed')

        resp = client.post('/api/jira/test-connection', headers=_auth(tenant_data['token_a']))
        assert resp.status_code == 400
        assert 'Cannot connect' in resp.get_json()['error']


# ---------------------------------------------------------------------------
# 3. test_disconnect -- Clears all credentials
# ---------------------------------------------------------------------------

class TestDisconnect:

    def test_disconnect_clears_credentials(self, client, tenant_data):
        """POST /api/jira/disconnect clears all Jira fields."""
        resp = client.post('/api/jira/disconnect', headers=_auth(tenant_data['token_a']))
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['connected'] is False

        # Verify status shows disconnected
        resp2 = client.get('/api/jira/status', headers=_auth(tenant_data['token_a']))
        assert resp2.get_json()['data']['connected'] is False

        # Restore for other tests
        db = SessionLocal()
        try:
            org = db.query(Organization).filter_by(id=tenant_data['org_a_id']).first()
            org.jira_site_url = 'https://orgA.atlassian.net'
            org.jira_user_email = 'admin@orgA.com'
            org.jira_api_token = 'fake-api-token-a'
            db.commit()
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 4. test_create_issue_from_test_result -- Mock Jira create, saves link
# ---------------------------------------------------------------------------

class TestCreateIssueFromTestResult:

    @patch('services.jira_service.requests.post')
    def test_create_issue_from_test_result(self, mock_post, client, tenant_data):
        """POST /api/jira/create-issue creates a Jira issue and saves a link."""
        mock_post.return_value = MagicMock(
            status_code=201,
            json=lambda: {'key': 'PROJ-42', 'id': '10042'},
        )

        resp = client.post(
            '/api/jira/create-issue',
            json={
                'test_result_id': tenant_data['result_a_id'],
                'project_key': 'PROJ',
                'issue_type': 'Bug',
            },
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 201
        data = resp.get_json()['data']
        assert data['jira_issue_key'] == 'PROJ-42'
        assert 'PROJ-42' in data['jira_issue_url']
        assert data['link_id'] is not None

        # Verify link is saved in DB
        db = SessionLocal()
        try:
            link = db.query(JiraIssueLink).filter_by(jira_issue_key='PROJ-42').first()
            assert link is not None
            assert link.test_case_id == tenant_data['case_a_id']
            assert link.test_result_id == tenant_data['result_a_id']
            assert link.jira_status == 'Open'
            assert str(link.tenant_id) == tenant_data['org_a_id']
        finally:
            db.close()

        # Verify Jira API was called with correct payload
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        payload = call_args[1]['json']
        assert payload['fields']['project']['key'] == 'PROJ'
        assert 'TC00001' in payload['fields']['summary']
        assert payload['fields']['issuetype']['name'] == 'Bug'

    def test_create_issue_missing_fields(self, client, tenant_data):
        """POST /api/jira/create-issue without required fields returns 400."""
        resp = client.post(
            '/api/jira/create-issue',
            json={'test_result_id': tenant_data['result_a_id']},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 400
        assert 'required' in resp.get_json()['error']


# ---------------------------------------------------------------------------
# 5. test_create_issue_jira_not_connected -- Returns error if no token
# ---------------------------------------------------------------------------

class TestCreateIssueJiraNotConnected:

    def test_create_issue_jira_not_connected(self, client, tenant_data):
        """POST /api/jira/create-issue returns error when Jira is not connected."""
        # Temporarily remove the Jira credentials
        db = SessionLocal()
        try:
            org = db.query(Organization).filter_by(id=tenant_data['org_a_id']).first()
            original_token = org.jira_api_token
            original_email = org.jira_user_email
            org.jira_api_token = None
            org.jira_user_email = None
            db.commit()
        finally:
            db.close()

        try:
            resp = client.post(
                '/api/jira/create-issue',
                json={
                    'test_result_id': tenant_data['result_a_id'],
                    'project_key': 'PROJ',
                },
                headers=_auth(tenant_data['token_a']),
            )
            assert resp.status_code == 400
            assert 'not connected' in resp.get_json()['error'].lower()
        finally:
            # Restore credentials
            db = SessionLocal()
            try:
                org = db.query(Organization).filter_by(id=tenant_data['org_a_id']).first()
                org.jira_api_token = original_token
                org.jira_user_email = original_email
                db.commit()
            finally:
                db.close()


# ---------------------------------------------------------------------------
# 6. test_webhook_updates_status -- Webhook updates jira_issue_links
# ---------------------------------------------------------------------------

class TestWebhookUpdatesStatus:

    def test_webhook_updates_status(self, client, tenant_data):
        """POST /api/jira/webhook updates existing Jira issue links."""
        # First, create a link in the database
        db = SessionLocal()
        try:
            link = JiraIssueLink(
                tenant_id=tenant_data['org_a_id'],
                test_case_id=tenant_data['case_a_id'],
                test_result_id=tenant_data['result_a_id'],
                jira_issue_key='PROJ-100',
                jira_issue_summary='Old Summary',
                jira_status='Open',
                last_synced_at=datetime.now(timezone.utc),
            )
            db.add(link)
            db.commit()
            link_id = link.id
        finally:
            db.close()

        # Send webhook payload
        webhook_payload = {
            'webhookEvent': 'jira:issue_updated',
            'issue': {
                'key': 'PROJ-100',
                'fields': {
                    'status': {'name': 'In Progress'},
                    'assignee': {'displayName': 'John Doe'},
                    'priority': {'name': 'High'},
                    'summary': 'Updated Summary',
                },
            },
        }

        resp = client.post('/api/jira/webhook', json=webhook_payload)
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['updated'] == 1
        assert data['issue_key'] == 'PROJ-100'
        assert data['new_status'] == 'In Progress'

        # Verify the link was updated in DB
        db = SessionLocal()
        try:
            updated_link = db.query(JiraIssueLink).filter_by(id=link_id).first()
            assert updated_link.jira_status == 'In Progress'
            assert updated_link.jira_assignee == 'John Doe'
            assert updated_link.jira_priority == 'High'
            assert updated_link.jira_issue_summary == 'Updated Summary'
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 7. test_webhook_ignores_unknown_events -- Non-update events ignored
# ---------------------------------------------------------------------------

class TestWebhookIgnoresUnknownEvents:

    def test_webhook_ignores_unknown_events(self, client, tenant_data):
        """POST /api/jira/webhook ignores events other than jira:issue_updated."""
        webhook_payload = {
            'webhookEvent': 'jira:issue_created',
            'issue': {
                'key': 'PROJ-999',
                'fields': {
                    'status': {'name': 'Open'},
                    'summary': 'New Issue',
                },
            },
        }

        resp = client.post('/api/jira/webhook', json=webhook_payload)
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['ignored'] is True

    def test_webhook_ignores_missing_issue_key(self, client, tenant_data):
        """POST /api/jira/webhook ignores payloads without issue key."""
        webhook_payload = {
            'webhookEvent': 'jira:issue_updated',
            'issue': {
                'fields': {
                    'status': {'name': 'Done'},
                },
            },
        }

        resp = client.post('/api/jira/webhook', json=webhook_payload)
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['ignored'] is True

    def test_webhook_no_auth_required(self, client, tenant_data):
        """POST /api/jira/webhook does not require authentication."""
        resp = client.post(
            '/api/jira/webhook',
            json={'webhookEvent': 'jira:issue_created', 'issue': {}},
        )
        # Should not return 401
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 8. test_sync_issue_status -- Manual sync updates link
# ---------------------------------------------------------------------------

class TestSyncIssueStatus:

    @patch('services.jira_service.requests.get')
    def test_sync_issue_status(self, mock_get, client, tenant_data):
        """POST /api/jira/sync/<link_id> fetches and updates issue status."""
        # Create a link
        db = SessionLocal()
        try:
            link = JiraIssueLink(
                tenant_id=tenant_data['org_a_id'],
                test_case_id=tenant_data['case_a_id'],
                test_result_id=tenant_data['result_a_id'],
                jira_issue_key='PROJ-200',
                jira_issue_summary='Original Summary',
                jira_status='Open',
                last_synced_at=datetime.now(timezone.utc),
            )
            db.add(link)
            db.commit()
            link_id = link.id
        finally:
            db.close()

        # Mock the Jira API response
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                'key': 'PROJ-200',
                'fields': {
                    'status': {'name': 'Done'},
                    'assignee': {'displayName': 'Jane Smith'},
                    'priority': {'name': 'Medium'},
                    'summary': 'Synced Summary',
                },
            },
        )

        resp = client.post(
            f'/api/jira/sync/{link_id}',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['jira_issue_key'] == 'PROJ-200'
        assert data['jira_status'] == 'Done'
        assert data['jira_assignee'] == 'Jane Smith'
        assert data['last_synced_at'] is not None

    def test_sync_nonexistent_link(self, client, tenant_data):
        """POST /api/jira/sync/<link_id> returns 404 for nonexistent link."""
        resp = client.post(
            '/api/jira/sync/99999',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404
        assert 'not found' in resp.get_json()['error'].lower()


# ---------------------------------------------------------------------------
# 9. test_get_project_links -- Returns all links for project
# ---------------------------------------------------------------------------

class TestGetProjectLinks:

    def test_get_project_links(self, client, tenant_data):
        """GET /api/jira/project-links/<id> returns all links for a project."""
        # Create two links for project A
        db = SessionLocal()
        try:
            link1 = JiraIssueLink(
                tenant_id=tenant_data['org_a_id'],
                test_case_id=tenant_data['case_a_id'],
                test_result_id=tenant_data['result_a_id'],
                jira_issue_key='PROJ-301',
                jira_issue_summary='First Bug',
                jira_status='Open',
                jira_assignee='Alice',
                jira_priority='High',
                last_synced_at=datetime.now(timezone.utc),
            )
            link2 = JiraIssueLink(
                tenant_id=tenant_data['org_a_id'],
                test_case_id=tenant_data['case_a_id'],
                test_result_id=tenant_data['result_a_id'],
                jira_issue_key='PROJ-302',
                jira_issue_summary='Second Bug',
                jira_status='In Progress',
                jira_assignee='Bob',
                jira_priority='Medium',
                last_synced_at=datetime.now(timezone.utc),
            )
            db.add_all([link1, link2])
            db.commit()
        finally:
            db.close()

        resp = client.get(
            f'/api/jira/project-links/{tenant_data["project_a_id"]}',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert len(data) == 2
        keys = {item['jira_issue_key'] for item in data}
        assert keys == {'PROJ-301', 'PROJ-302'}

        # Verify all fields are present
        for item in data:
            assert 'id' in item
            assert 'test_case_id' in item
            assert 'test_result_id' in item
            assert 'jira_issue_key' in item
            assert 'jira_issue_summary' in item
            assert 'jira_status' in item
            assert 'jira_assignee' in item
            assert 'jira_priority' in item
            assert 'last_synced_at' in item

    def test_get_project_links_empty(self, client, tenant_data):
        """GET /api/jira/project-links/<id> returns empty list when no links."""
        resp = client.get(
            f'/api/jira/project-links/{tenant_data["project_a_id"]}',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data == []

    def test_get_project_links_nonexistent_project(self, client, tenant_data):
        """GET /api/jira/project-links/<id> returns 404 for nonexistent project."""
        resp = client.get(
            '/api/jira/project-links/99999',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404
        assert 'not found' in resp.get_json()['error'].lower()


# ---------------------------------------------------------------------------
# 10. test_connection_status -- Returns connected/disconnected
# ---------------------------------------------------------------------------

class TestConnectionStatus:

    def test_connection_status_connected(self, client, tenant_data):
        """GET /api/jira/status returns connected when credentials exist."""
        resp = client.get('/api/jira/status', headers=_auth(tenant_data['token_a']))
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['connected'] is True
        assert data['site_url'] is not None
        assert data['user_email'] is not None

    def test_connection_status_disconnected(self, client, tenant_data):
        """GET /api/jira/status returns disconnected when no credentials."""
        # Temporarily remove credentials
        db = SessionLocal()
        try:
            org = db.query(Organization).filter_by(id=tenant_data['org_a_id']).first()
            original_token = org.jira_api_token
            original_email = org.jira_user_email
            org.jira_api_token = None
            org.jira_user_email = None
            db.commit()
        finally:
            db.close()

        try:
            resp = client.get('/api/jira/status', headers=_auth(tenant_data['token_a']))
            assert resp.status_code == 200
            data = resp.get_json()['data']
            assert data['connected'] is False
            assert data['site_url'] is None
            assert data['user_email'] is None
        finally:
            # Restore credentials
            db = SessionLocal()
            try:
                org = db.query(Organization).filter_by(id=tenant_data['org_a_id']).first()
                org.jira_api_token = original_token
                org.jira_user_email = original_email
                db.commit()
            finally:
                db.close()


# ---------------------------------------------------------------------------
# 11. test_tenant_isolation -- Can't access other tenant's links
# ---------------------------------------------------------------------------

class TestTenantIsolation:

    def test_tenant_b_cannot_sync_tenant_a_link(self, client, tenant_data):
        """Tenant B cannot sync a Jira link belonging to Tenant A."""
        # Create a link for Tenant A
        db = SessionLocal()
        try:
            link = JiraIssueLink(
                tenant_id=tenant_data['org_a_id'],
                test_case_id=tenant_data['case_a_id'],
                test_result_id=tenant_data['result_a_id'],
                jira_issue_key='PROJ-400',
                jira_issue_summary='Tenant A Bug',
                jira_status='Open',
                last_synced_at=datetime.now(timezone.utc),
            )
            db.add(link)
            db.commit()
            link_id = link.id
        finally:
            db.close()

        # Tenant B tries to sync Tenant A's link
        resp = client.post(
            f'/api/jira/sync/{link_id}',
            headers=_auth(tenant_data['token_b']),
        )
        assert resp.status_code == 404
        assert 'not found' in resp.get_json()['error'].lower()

    def test_tenant_b_cannot_see_tenant_a_project_links(self, client, tenant_data):
        """Tenant B cannot see Jira links for Tenant A's project."""
        # Create a link for Tenant A's project
        db = SessionLocal()
        try:
            link = JiraIssueLink(
                tenant_id=tenant_data['org_a_id'],
                test_case_id=tenant_data['case_a_id'],
                test_result_id=tenant_data['result_a_id'],
                jira_issue_key='PROJ-500',
                jira_issue_summary='Tenant A Project Bug',
                jira_status='Open',
                last_synced_at=datetime.now(timezone.utc),
            )
            db.add(link)
            db.commit()
        finally:
            db.close()

        # Tenant B tries to get Tenant A's project links
        resp = client.get(
            f'/api/jira/project-links/{tenant_data["project_a_id"]}',
            headers=_auth(tenant_data['token_b']),
        )
        # Should return 404 because tenant_filter prevents finding the project
        assert resp.status_code == 404

    @patch('services.jira_service.requests.post')
    def test_tenant_b_cannot_create_issue_for_tenant_a_result(self, mock_post, client, tenant_data):
        """Tenant B cannot create a Jira issue for Tenant A's test result."""
        mock_post.return_value = MagicMock(
            status_code=201,
            json=lambda: {'key': 'PROJ-999', 'id': '10999'},
        )

        resp = client.post(
            '/api/jira/create-issue',
            json={
                'test_result_id': tenant_data['result_a_id'],
                'project_key': 'PROJ',
            },
            headers=_auth(tenant_data['token_b']),
        )
        assert resp.status_code == 400
        assert 'not found' in resp.get_json()['error'].lower()

    def test_requires_auth(self, client, tenant_data):
        """All protected endpoints require authentication."""
        endpoints = [
            ('POST', '/api/jira/connect'),
            ('POST', '/api/jira/test-connection'),
            ('POST', '/api/jira/disconnect'),
            ('GET', '/api/jira/status'),
            ('GET', '/api/jira/projects'),
            ('POST', '/api/jira/create-issue'),
            ('POST', '/api/jira/sync/1'),
            ('GET', '/api/jira/project-links/1'),
        ]
        for method, path in endpoints:
            if method == 'GET':
                resp = client.get(path)
            else:
                resp = client.post(path, json={})
            assert resp.status_code == 401, f"{method} {path} should require auth"

    def test_webhook_does_not_require_auth(self, client, tenant_data):
        """Webhook endpoint does not require authentication."""
        resp = client.post(
            '/api/jira/webhook',
            json={'webhookEvent': 'test', 'issue': {}},
        )
        assert resp.status_code != 401


# ---------------------------------------------------------------------------
# Additional edge case tests
# ---------------------------------------------------------------------------

class TestEdgeCases:

    @patch('services.jira_service.requests.post')
    def test_create_issue_jira_api_error(self, mock_post, client, tenant_data):
        """Create issue returns error when Jira API rejects the request."""
        mock_post.return_value = MagicMock(
            status_code=400,
            text='Project not found',
        )

        resp = client.post(
            '/api/jira/create-issue',
            json={
                'test_result_id': tenant_data['result_a_id'],
                'project_key': 'NONEXISTENT',
            },
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 400
        assert 'Failed to create Jira issue' in resp.get_json()['error']

    @patch('services.jira_service.requests.get')
    def test_list_projects(self, mock_get, client, tenant_data):
        """GET /api/jira/projects returns project list from Jira."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {'key': 'PROJ', 'name': 'Main Project', 'id': '10001'},
                {'key': 'QA', 'name': 'QA Project', 'id': '10002'},
            ],
        )

        resp = client.get('/api/jira/projects', headers=_auth(tenant_data['token_a']))
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert len(data) == 2
        assert data[0]['key'] == 'PROJ'
        assert data[1]['name'] == 'QA Project'

    def test_webhook_invalid_payload(self, client):
        """Webhook with non-JSON body returns 400."""
        resp = client.post(
            '/api/jira/webhook',
            data='not json',
            content_type='text/plain',
        )
        assert resp.status_code == 400
