"""
Tests for the API-TestCase coverage module.

Covers link creation, duplicate rejection, unlinking, coverage dashboard
calculations, cross-reference queries, coverage alerts, and tenant isolation.
"""
import pytest
from datetime import datetime, timedelta, timezone

from app_factory import create_app
from database.models import (
    Organization, User, ApiEndpoint, TestCase, ApiTestcaseLink,
    ApiCheckHistory, TestCaseTag, TestProject, TestResult,
    ProductTag, JiraIssueLink,
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
            name='Cov Org A',
            slug='cov-org-a',
            plan='trial',
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
            subscription_status='trialing',
        )
        db.add(org_a)
        db.flush()

        user_a = User(
            tenant_id=org_a.id,
            username='cov_user_a',
            email='cov_a@test.com',
            password_hash=hash_password('Password123!'),
            role='admin',
        )
        db.add(user_a)
        db.flush()

        # -- Tenant B ---------------------------------------------------------
        org_b = Organization(
            name='Cov Org B',
            slug='cov-org-b',
            plan='trial',
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
            subscription_status='trialing',
        )
        db.add(org_b)
        db.flush()

        user_b = User(
            tenant_id=org_b.id,
            username='cov_user_b',
            email='cov_b@test.com',
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
            'user_a_id': str(user_a.id),
            'user_b_id': str(user_b.id),
            'token_a': token_a,
            'token_b': token_b,
        }
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _clean_test_data():
    """Remove all coverage-related data before each test."""
    db = SessionLocal()
    try:
        db.query(ApiTestcaseLink).delete()
        db.query(TestResult).delete()
        db.query(TestCaseTag).delete()
        db.query(TestCase).delete()
        db.query(TestProject).delete()
        db.query(ProductTag).delete()
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


# ---------------------------------------------------------------------------
# Helpers -- create test data via API
# ---------------------------------------------------------------------------

def _create_endpoint(client, token, **overrides):
    """Create an API endpoint via the API."""
    payload = {
        'name': 'Test API',
        'url': 'https://api.example.com/health',
        'method': 'GET',
    }
    payload.update(overrides)
    return client.post('/api/endpoints', json=payload, headers=_auth(token))


def _create_test_case(client, token, **overrides):
    """Create a test case via the API."""
    payload = {
        'title': 'Test Login Feature',
        'priority': 'high',
    }
    payload.update(overrides)
    return client.post('/api/test-cases', json=payload, headers=_auth(token))


def _link(client, token, api_id, test_case_id, link_type='covers'):
    """Create a coverage link via the API."""
    return client.post(
        '/api/coverage/links',
        json={'api_id': api_id, 'test_case_id': test_case_id, 'link_type': link_type},
        headers=_auth(token),
    )


def _set_endpoint_status(endpoint_id, status, last_error=None):
    """Directly set an endpoint's status in the database."""
    db = SessionLocal()
    try:
        ep = db.query(ApiEndpoint).filter_by(id=endpoint_id).first()
        ep.status = status
        ep.last_error = last_error
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 1. Create link returns 201
# ---------------------------------------------------------------------------

class TestLinkApiToTestCase:

    def test_link_api_to_test_case(self, client, tenant_data):
        """Creating a link between API and test case returns 201."""
        ep_resp = _create_endpoint(client, tenant_data['token_a'], name='Link API')
        ep_id = ep_resp.get_json()['data']['id']

        case_resp = _create_test_case(client, tenant_data['token_a'], title='Link Case')
        case_id = case_resp.get_json()['data']['id']

        resp = _link(client, tenant_data['token_a'], ep_id, case_id)
        assert resp.status_code == 201
        data = resp.get_json()['data']
        assert data['api_id'] == ep_id
        assert data['test_case_id'] == case_id
        assert data['link_type'] == 'covers'

    def test_link_nonexistent_api(self, client, tenant_data):
        """Linking a nonexistent API returns 404."""
        case_resp = _create_test_case(client, tenant_data['token_a'], title='No API Case')
        case_id = case_resp.get_json()['data']['id']

        resp = _link(client, tenant_data['token_a'], 99999, case_id)
        assert resp.status_code == 404
        assert 'API endpoint not found' in resp.get_json()['error']

    def test_link_nonexistent_test_case(self, client, tenant_data):
        """Linking a nonexistent test case returns 404."""
        ep_resp = _create_endpoint(client, tenant_data['token_a'], name='No Case API')
        ep_id = ep_resp.get_json()['data']['id']

        resp = _link(client, tenant_data['token_a'], ep_id, 99999)
        assert resp.status_code == 404
        assert 'Test case not found' in resp.get_json()['error']

    def test_link_missing_fields(self, client, tenant_data):
        """Missing api_id or test_case_id returns 400."""
        resp = client.post(
            '/api/coverage/links',
            json={'api_id': 1},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 2. Duplicate link rejected
# ---------------------------------------------------------------------------

class TestLinkDuplicateRejected:

    def test_link_duplicate_rejected(self, client, tenant_data):
        """Creating the same link twice returns 409."""
        ep_resp = _create_endpoint(client, tenant_data['token_a'], name='Dup API')
        ep_id = ep_resp.get_json()['data']['id']

        case_resp = _create_test_case(client, tenant_data['token_a'], title='Dup Case')
        case_id = case_resp.get_json()['data']['id']

        # First link -- should succeed
        resp1 = _link(client, tenant_data['token_a'], ep_id, case_id)
        assert resp1.status_code == 201

        # Second link -- should be rejected
        resp2 = _link(client, tenant_data['token_a'], ep_id, case_id)
        assert resp2.status_code == 409
        assert 'already exists' in resp2.get_json()['error'].lower()


# ---------------------------------------------------------------------------
# 3. Unlink
# ---------------------------------------------------------------------------

class TestUnlink:

    def test_unlink(self, client, tenant_data):
        """Removing a link returns 200."""
        ep_resp = _create_endpoint(client, tenant_data['token_a'], name='Unlink API')
        ep_id = ep_resp.get_json()['data']['id']

        case_resp = _create_test_case(client, tenant_data['token_a'], title='Unlink Case')
        case_id = case_resp.get_json()['data']['id']

        _link(client, tenant_data['token_a'], ep_id, case_id)

        resp = client.delete(
            '/api/coverage/links',
            json={'api_id': ep_id, 'test_case_id': case_id},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        assert resp.get_json()['data']['removed'] is True

    def test_unlink_nonexistent_link(self, client, tenant_data):
        """Removing a nonexistent link returns 404."""
        ep_resp = _create_endpoint(client, tenant_data['token_a'], name='No Link API')
        ep_id = ep_resp.get_json()['data']['id']

        case_resp = _create_test_case(client, tenant_data['token_a'], title='No Link Case')
        case_id = case_resp.get_json()['data']['id']

        resp = client.delete(
            '/api/coverage/links',
            json={'api_id': ep_id, 'test_case_id': case_id},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404

    def test_unlink_nonexistent_api(self, client, tenant_data):
        """Unlinking with nonexistent API returns 404."""
        resp = client.delete(
            '/api/coverage/links',
            json={'api_id': 99999, 'test_case_id': 1},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 4. Coverage dashboard -- all covered
# ---------------------------------------------------------------------------

class TestCoverageDashboardAllCovered:

    def test_coverage_dashboard_all_covered(self, client, tenant_data):
        """100% coverage when all APIs have linked test cases."""
        # Create 2 APIs
        ep1 = _create_endpoint(client, tenant_data['token_a'], name='Cov API 1').get_json()['data']['id']
        ep2 = _create_endpoint(client, tenant_data['token_a'], name='Cov API 2').get_json()['data']['id']

        # Create 2 test cases
        tc1 = _create_test_case(client, tenant_data['token_a'], title='Cov Case 1').get_json()['data']['id']
        tc2 = _create_test_case(client, tenant_data['token_a'], title='Cov Case 2').get_json()['data']['id']

        # Link both
        _link(client, tenant_data['token_a'], ep1, tc1)
        _link(client, tenant_data['token_a'], ep2, tc2)

        resp = client.get('/api/coverage/dashboard', headers=_auth(tenant_data['token_a']))
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['total_apis'] == 2
        assert data['covered_apis'] == 2
        assert data['uncovered_apis'] == 0
        assert data['coverage_percent'] == 100.0
        assert data['uncovered_api_list'] == []


# ---------------------------------------------------------------------------
# 5. Coverage dashboard -- partial
# ---------------------------------------------------------------------------

class TestCoverageDashboardPartial:

    def test_coverage_dashboard_partial(self, client, tenant_data):
        """Correct percentage with some uncovered APIs."""
        # Create 3 APIs
        ep1 = _create_endpoint(client, tenant_data['token_a'], name='Part API 1').get_json()['data']['id']
        ep2 = _create_endpoint(client, tenant_data['token_a'], name='Part API 2').get_json()['data']['id']
        _create_endpoint(client, tenant_data['token_a'], name='Part API 3')

        # Create 1 test case
        tc1 = _create_test_case(client, tenant_data['token_a'], title='Part Case 1').get_json()['data']['id']

        # Link only 2 APIs
        _link(client, tenant_data['token_a'], ep1, tc1)
        _link(client, tenant_data['token_a'], ep2, tc1)

        resp = client.get('/api/coverage/dashboard', headers=_auth(tenant_data['token_a']))
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['total_apis'] == 3
        assert data['covered_apis'] == 2
        assert data['uncovered_apis'] == 1
        assert data['coverage_percent'] == 66.7
        assert len(data['uncovered_api_list']) == 1
        assert data['uncovered_api_list'][0]['name'] == 'Part API 3'


# ---------------------------------------------------------------------------
# 6. Coverage dashboard -- none
# ---------------------------------------------------------------------------

class TestCoverageDashboardNone:

    def test_coverage_dashboard_none(self, client, tenant_data):
        """0% coverage with no links."""
        _create_endpoint(client, tenant_data['token_a'], name='None API 1')
        _create_endpoint(client, tenant_data['token_a'], name='None API 2')

        resp = client.get('/api/coverage/dashboard', headers=_auth(tenant_data['token_a']))
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['total_apis'] == 2
        assert data['covered_apis'] == 0
        assert data['uncovered_apis'] == 2
        assert data['coverage_percent'] == 0.0
        assert len(data['uncovered_api_list']) == 2

    def test_coverage_dashboard_no_apis(self, client, tenant_data):
        """0% coverage with no APIs at all."""
        resp = client.get('/api/coverage/dashboard', headers=_auth(tenant_data['token_a']))
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['total_apis'] == 0
        assert data['coverage_percent'] == 0


# ---------------------------------------------------------------------------
# 7. Uncovered API list
# ---------------------------------------------------------------------------

class TestUncoveredApiList:

    def test_uncovered_api_list(self, client, tenant_data):
        """Dashboard returns correct details for uncovered APIs."""
        _create_endpoint(client, tenant_data['token_a'], name='Uncov API 1', url='https://api1.example.com')
        ep2 = _create_endpoint(client, tenant_data['token_a'], name='Uncov API 2', url='https://api2.example.com')
        ep2_id = ep2.get_json()['data']['id']

        tc = _create_test_case(client, tenant_data['token_a'], title='Uncov Case').get_json()['data']['id']

        # Only link API 2
        _link(client, tenant_data['token_a'], ep2_id, tc)

        resp = client.get('/api/coverage/dashboard', headers=_auth(tenant_data['token_a']))
        data = resp.get_json()['data']

        assert data['uncovered_apis'] == 1
        uncovered = data['uncovered_api_list']
        assert len(uncovered) == 1
        assert uncovered[0]['name'] == 'Uncov API 1'
        assert uncovered[0]['url'] == 'https://api1.example.com'
        assert 'id' in uncovered[0]
        assert 'status' in uncovered[0]


# ---------------------------------------------------------------------------
# 8. API with linked cases
# ---------------------------------------------------------------------------

class TestApiWithLinkedCases:

    def test_api_with_linked_cases(self, client, tenant_data):
        """Get API shows its linked test cases."""
        ep = _create_endpoint(client, tenant_data['token_a'], name='API With Cases')
        ep_id = ep.get_json()['data']['id']

        tc1 = _create_test_case(client, tenant_data['token_a'], title='Linked Case 1').get_json()['data']['id']
        tc2 = _create_test_case(client, tenant_data['token_a'], title='Linked Case 2').get_json()['data']['id']

        _link(client, tenant_data['token_a'], ep_id, tc1)
        _link(client, tenant_data['token_a'], ep_id, tc2)

        resp = client.get(
            f'/api/coverage/api/{ep_id}/cases',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']

        assert data['api']['id'] == ep_id
        assert data['api']['name'] == 'API With Cases'
        assert len(data['linked_test_cases']) == 2
        titles = {c['title'] for c in data['linked_test_cases']}
        assert titles == {'Linked Case 1', 'Linked Case 2'}

    def test_api_with_no_linked_cases(self, client, tenant_data):
        """Get API with no links returns empty list."""
        ep = _create_endpoint(client, tenant_data['token_a'], name='API No Cases')
        ep_id = ep.get_json()['data']['id']

        resp = client.get(
            f'/api/coverage/api/{ep_id}/cases',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['linked_test_cases'] == []

    def test_api_nonexistent(self, client, tenant_data):
        """Get nonexistent API returns 404."""
        resp = client.get(
            '/api/coverage/api/99999/cases',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 9. Case with linked APIs
# ---------------------------------------------------------------------------

class TestCaseWithLinkedApis:

    def test_case_with_linked_apis(self, client, tenant_data):
        """Get case shows its linked API endpoints."""
        tc = _create_test_case(client, tenant_data['token_a'], title='Case With APIs')
        tc_id = tc.get_json()['data']['id']

        ep1 = _create_endpoint(client, tenant_data['token_a'], name='Linked API 1').get_json()['data']['id']
        ep2 = _create_endpoint(client, tenant_data['token_a'], name='Linked API 2').get_json()['data']['id']

        _link(client, tenant_data['token_a'], ep1, tc_id)
        _link(client, tenant_data['token_a'], ep2, tc_id)

        resp = client.get(
            f'/api/coverage/case/{tc_id}/apis',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']

        assert data['test_case']['title'] == 'Case With APIs'
        assert len(data['linked_apis']) == 2
        names = {a['name'] for a in data['linked_apis']}
        assert names == {'Linked API 1', 'Linked API 2'}

    def test_case_nonexistent(self, client, tenant_data):
        """Get nonexistent case returns 404."""
        resp = client.get(
            '/api/coverage/case/99999/apis',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 10. Alert: unhealthy API with linked test cases
# ---------------------------------------------------------------------------

class TestAlertsUnhealthyWithCases:

    def test_alerts_unhealthy_with_cases(self, client, tenant_data):
        """Alert raised when unhealthy API has linked test cases."""
        ep = _create_endpoint(client, tenant_data['token_a'], name='Unhealthy API')
        ep_id = ep.get_json()['data']['id']

        tc = _create_test_case(client, tenant_data['token_a'], title='Alert Case')
        tc_id = tc.get_json()['data']['id']

        _link(client, tenant_data['token_a'], ep_id, tc_id)

        # Set endpoint to unhealthy
        _set_endpoint_status(ep_id, 'unhealthy', 'Connection refused')

        resp = client.get('/api/coverage/alerts', headers=_auth(tenant_data['token_a']))
        assert resp.status_code == 200
        alerts = resp.get_json()['data']
        assert alerts['total_alerts'] >= 1

        # Find the specific alert
        unhealthy_alerts = [a for a in alerts['data'] if a['type'] == 'unhealthy_api_with_cases']
        assert len(unhealthy_alerts) == 1
        alert = unhealthy_alerts[0]
        assert alert['api']['id'] == ep_id
        assert alert['api']['name'] == 'Unhealthy API'
        assert alert['api']['last_error'] == 'Connection refused'
        assert len(alert['affected_test_cases']) == 1
        assert alert['affected_test_cases'][0]['title'] == 'Alert Case'


# ---------------------------------------------------------------------------
# 11. Alert: uncovered unhealthy API
# ---------------------------------------------------------------------------

class TestAlertsUncoveredUnhealthy:

    def test_alerts_uncovered_unhealthy(self, client, tenant_data):
        """Alert raised when unhealthy API has no linked test cases."""
        ep = _create_endpoint(client, tenant_data['token_a'], name='Uncovered Unhealthy')
        ep_id = ep.get_json()['data']['id']

        _set_endpoint_status(ep_id, 'unhealthy', 'Timeout')

        resp = client.get('/api/coverage/alerts', headers=_auth(tenant_data['token_a']))
        assert resp.status_code == 200
        alerts = resp.get_json()['data']
        assert alerts['total_alerts'] >= 1

        uncovered_alerts = [a for a in alerts['data'] if a['type'] == 'uncovered_unhealthy_api']
        assert len(uncovered_alerts) == 1
        alert = uncovered_alerts[0]
        assert alert['api']['id'] == ep_id
        assert alert['api']['name'] == 'Uncovered Unhealthy'
        assert alert['api']['last_error'] == 'Timeout'
        assert alert['affected_test_cases'] == []

    def test_no_alerts_when_all_healthy(self, client, tenant_data):
        """No alerts when all APIs are healthy."""
        _create_endpoint(client, tenant_data['token_a'], name='Healthy API')

        resp = client.get('/api/coverage/alerts', headers=_auth(tenant_data['token_a']))
        assert resp.status_code == 200
        alerts = resp.get_json()['data']
        assert alerts['total_alerts'] == 0
        assert alerts['data'] == []


# ---------------------------------------------------------------------------
# 12. Tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:

    def test_tenant_isolation(self, client, tenant_data):
        """Cannot link resources across tenants."""
        # Create API in Tenant A
        ep_a = _create_endpoint(client, tenant_data['token_a'], name='A API')
        ep_a_id = ep_a.get_json()['data']['id']

        # Create test case in Tenant B
        tc_b = _create_test_case(client, tenant_data['token_b'], title='B Case')
        tc_b_id = tc_b.get_json()['data']['id']

        # Try to link Tenant A's API with Tenant B's test case (using Tenant A's token)
        resp = _link(client, tenant_data['token_a'], ep_a_id, tc_b_id)
        assert resp.status_code == 404
        assert 'Test case not found' in resp.get_json()['error']

    def test_tenant_a_cannot_see_tenant_b_coverage(self, client, tenant_data):
        """Coverage dashboard only shows current tenant's data."""
        # Create and link in Tenant B
        ep_b = _create_endpoint(client, tenant_data['token_b'], name='B Coverage API')
        ep_b_id = ep_b.get_json()['data']['id']

        tc_b = _create_test_case(client, tenant_data['token_b'], title='B Coverage Case')
        tc_b_id = tc_b.get_json()['data']['id']

        _link(client, tenant_data['token_b'], ep_b_id, tc_b_id)

        # Tenant A's dashboard should show 0 APIs
        resp_a = client.get('/api/coverage/dashboard', headers=_auth(tenant_data['token_a']))
        data_a = resp_a.get_json()['data']
        assert data_a['total_apis'] == 0

        # Tenant B's dashboard should show 1 covered API
        resp_b = client.get('/api/coverage/dashboard', headers=_auth(tenant_data['token_b']))
        data_b = resp_b.get_json()['data']
        assert data_b['total_apis'] == 1
        assert data_b['covered_apis'] == 1

    def test_tenant_a_cannot_view_tenant_b_api_cases(self, client, tenant_data):
        """Tenant A cannot see Tenant B's API linked cases."""
        ep_b = _create_endpoint(client, tenant_data['token_b'], name='B Secret API')
        ep_b_id = ep_b.get_json()['data']['id']

        resp = client.get(
            f'/api/coverage/api/{ep_b_id}/cases',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404

    def test_tenant_a_cannot_view_tenant_b_case_apis(self, client, tenant_data):
        """Tenant A cannot see Tenant B's case linked APIs."""
        tc_b = _create_test_case(client, tenant_data['token_b'], title='B Secret Case')
        tc_b_id = tc_b.get_json()['data']['id']

        resp = client.get(
            f'/api/coverage/case/{tc_b_id}/apis',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404

    def test_tenant_a_cannot_unlink_tenant_b_resources(self, client, tenant_data):
        """Tenant A cannot unlink Tenant B's resources."""
        ep_b = _create_endpoint(client, tenant_data['token_b'], name='B Unlink API')
        ep_b_id = ep_b.get_json()['data']['id']

        tc_b = _create_test_case(client, tenant_data['token_b'], title='B Unlink Case')
        tc_b_id = tc_b.get_json()['data']['id']

        _link(client, tenant_data['token_b'], ep_b_id, tc_b_id)

        resp = client.delete(
            '/api/coverage/links',
            json={'api_id': ep_b_id, 'test_case_id': tc_b_id},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404
