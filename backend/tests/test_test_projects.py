"""
Tests for the test project management module.

Covers project CRUD, test case assignment, test result tracking (UPSERT),
statistics calculation, completion rate, and tenant isolation.
"""
import pytest
from datetime import datetime, timedelta, timezone

from app_factory import create_app
from database.models import (
    Organization, User, TestProject, TestCase, TestResult,
    TestCaseTag, ProductTag, ApiEndpoint, ApiCheckHistory,
    ApiTestcaseLink, JiraIssueLink,
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
            name='TP Org A',
            slug='tp-org-a',
            plan='trial',
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
            subscription_status='trialing',
        )
        db.add(org_a)
        db.flush()

        user_a = User(
            tenant_id=org_a.id,
            username='tp_user_a',
            email='tp_a@test.com',
            password_hash=hash_password('Password123!'),
            role='admin',
        )
        db.add(user_a)
        db.flush()

        # -- Tenant B ---------------------------------------------------------
        org_b = Organization(
            name='TP Org B',
            slug='tp-org-b',
            plan='trial',
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
            subscription_status='trialing',
        )
        db.add(org_b)
        db.flush()

        user_b = User(
            tenant_id=org_b.id,
            username='tp_user_b',
            email='tp_b@test.com',
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
    """Remove all test projects, results, and test cases before each test."""
    db = SessionLocal()
    try:
        db.query(TestResult).delete()
        db.query(TestCaseTag).delete()
        db.query(TestCase).delete()
        db.query(TestProject).delete()
        db.query(ProductTag).delete()
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


def _create_project(client, token, **overrides):
    """Helper -- create a test project via the API and return the response."""
    payload = {
        'name': 'Sprint 1 Testing',
        'description': 'Test project for Sprint 1',
        'status': 'draft',
    }
    payload.update(overrides)
    return client.post(
        '/api/test-projects',
        json=payload,
        headers=_auth(token),
    )


def _create_test_case(client, token, **overrides):
    """Helper -- create a test case via the API and return the response."""
    payload = {
        'title': 'Test Login Feature',
        'priority': 'high',
    }
    payload.update(overrides)
    return client.post(
        '/api/test-cases',
        json=payload,
        headers=_auth(token),
    )


# ---------------------------------------------------------------------------
# 1. Create project
# ---------------------------------------------------------------------------

class TestCreateProject:

    def test_create_project(self, client, tenant_data):
        """Create returns 201 with correct fields."""
        resp = _create_project(client, tenant_data['token_a'])
        assert resp.status_code == 201
        data = resp.get_json()['data']

        assert data['name'] == 'Sprint 1 Testing'
        assert data['description'] == 'Test project for Sprint 1'
        assert data['status'] == 'draft'
        assert 'id' in data
        assert 'created_at' in data
        assert data['stats']['total'] == 0

    def test_create_project_missing_name(self, client, tenant_data):
        resp = client.post(
            '/api/test-projects',
            json={'description': 'No name'},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 400
        assert 'name' in resp.get_json()['error'].lower()

    def test_create_project_duplicate_name(self, client, tenant_data):
        _create_project(client, tenant_data['token_a'], name='Unique Project')
        resp = _create_project(client, tenant_data['token_a'], name='Unique Project')
        assert resp.status_code == 400
        assert 'already exists' in resp.get_json()['error']

    def test_create_project_invalid_status(self, client, tenant_data):
        resp = _create_project(client, tenant_data['token_a'], status='invalid')
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 2. List projects with stats
# ---------------------------------------------------------------------------

class TestListProjectsWithStats:

    def test_list_projects_with_stats(self, client, tenant_data):
        """List includes stats for each project."""
        # Create a project
        proj_resp = _create_project(client, tenant_data['token_a'])
        project_id = proj_resp.get_json()['data']['id']

        # Create and assign a test case
        case_resp = _create_test_case(client, tenant_data['token_a'], title='Case 1')
        case_id = case_resp.get_json()['data']['id']

        client.post(
            f'/api/test-projects/{project_id}/assign-cases',
            json={'test_case_ids': [case_id]},
            headers=_auth(tenant_data['token_a']),
        )

        # Mark it as pass
        client.put(
            f'/api/test-projects/{project_id}/results',
            json={'test_case_id': case_id, 'status': 'pass'},
            headers=_auth(tenant_data['token_a']),
        )

        # List projects
        resp = client.get('/api/test-projects', headers=_auth(tenant_data['token_a']))
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert len(data) == 1

        stats = data[0]['stats']
        assert stats['total'] == 1
        assert stats['pass_count'] == 1
        assert stats['fail_count'] == 0
        assert stats['not_tested_count'] == 0
        assert stats['completion_rate'] == 100.0


# ---------------------------------------------------------------------------
# 3. Get project detail
# ---------------------------------------------------------------------------

class TestGetProjectDetail:

    def test_get_project_detail(self, client, tenant_data):
        """Get includes test cases and results."""
        # Create project
        proj_resp = _create_project(client, tenant_data['token_a'])
        project_id = proj_resp.get_json()['data']['id']

        # Create test cases
        case1_resp = _create_test_case(client, tenant_data['token_a'], title='Case A')
        case2_resp = _create_test_case(client, tenant_data['token_a'], title='Case B')
        case1_id = case1_resp.get_json()['data']['id']
        case2_id = case2_resp.get_json()['data']['id']

        # Assign cases to project
        client.post(
            f'/api/test-projects/{project_id}/assign-cases',
            json={'test_case_ids': [case1_id, case2_id]},
            headers=_auth(tenant_data['token_a']),
        )

        # Set a result for case 1
        client.put(
            f'/api/test-projects/{project_id}/results',
            json={'test_case_id': case1_id, 'status': 'pass'},
            headers=_auth(tenant_data['token_a']),
        )

        # Get project detail
        resp = client.get(
            f'/api/test-projects/{project_id}',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']

        assert data['name'] == 'Sprint 1 Testing'
        assert 'test_cases' in data
        assert len(data['test_cases']) == 2

        # Case A should have a result
        case_a = next(c for c in data['test_cases'] if c['title'] == 'Case A')
        assert case_a['result'] is not None
        assert case_a['result']['status'] == 'pass'

        # Case B should have no result
        case_b = next(c for c in data['test_cases'] if c['title'] == 'Case B')
        assert case_b['result'] is None

    def test_get_nonexistent_project(self, client, tenant_data):
        resp = client.get(
            '/api/test-projects/99999',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 4. Update project
# ---------------------------------------------------------------------------

class TestUpdateProject:

    def test_update_project(self, client, tenant_data):
        """Update fields returns updated data."""
        create_resp = _create_project(client, tenant_data['token_a'])
        project_id = create_resp.get_json()['data']['id']

        resp = client.put(
            f'/api/test-projects/{project_id}',
            json={
                'name': 'Updated Project',
                'description': 'New description',
                'status': 'in_progress',
            },
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['name'] == 'Updated Project'
        assert data['description'] == 'New description'
        assert data['status'] == 'in_progress'

    def test_update_nonexistent_project(self, client, tenant_data):
        resp = client.put(
            '/api/test-projects/99999',
            json={'name': 'Ghost'},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 5. Delete project
# ---------------------------------------------------------------------------

class TestDeleteProject:

    def test_delete_project(self, client, tenant_data):
        """Delete cascades results and unlinks cases."""
        # Create project with a case and result
        proj_resp = _create_project(client, tenant_data['token_a'])
        project_id = proj_resp.get_json()['data']['id']

        case_resp = _create_test_case(client, tenant_data['token_a'], title='Del Case')
        case_id = case_resp.get_json()['data']['id']

        client.post(
            f'/api/test-projects/{project_id}/assign-cases',
            json={'test_case_ids': [case_id]},
            headers=_auth(tenant_data['token_a']),
        )

        client.put(
            f'/api/test-projects/{project_id}/results',
            json={'test_case_id': case_id, 'status': 'pass'},
            headers=_auth(tenant_data['token_a']),
        )

        # Delete
        resp = client.delete(
            f'/api/test-projects/{project_id}',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200

        # Project is gone
        resp = client.get(
            f'/api/test-projects/{project_id}',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404

        # Test case still exists but test_project_id is unlinked
        case_resp = client.get(
            f'/api/test-cases/{case_id}',
            headers=_auth(tenant_data['token_a']),
        )
        assert case_resp.status_code == 200
        assert case_resp.get_json()['data']['test_project_id'] is None

        # Test result is gone (verify in DB)
        db = SessionLocal()
        try:
            count = db.query(TestResult).filter_by(project_id=project_id).count()
            assert count == 0
        finally:
            db.close()

    def test_delete_nonexistent_project(self, client, tenant_data):
        resp = client.delete(
            '/api/test-projects/99999',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 6. Assign test cases
# ---------------------------------------------------------------------------

class TestAssignTestCases:

    def test_assign_test_cases(self, client, tenant_data):
        """Assign cases updates their project_id."""
        # Create project
        proj_resp = _create_project(client, tenant_data['token_a'])
        project_id = proj_resp.get_json()['data']['id']

        # Create cases
        case1_resp = _create_test_case(client, tenant_data['token_a'], title='Assign Case 1')
        case2_resp = _create_test_case(client, tenant_data['token_a'], title='Assign Case 2')
        case1_id = case1_resp.get_json()['data']['id']
        case2_id = case2_resp.get_json()['data']['id']

        # Assign
        resp = client.post(
            f'/api/test-projects/{project_id}/assign-cases',
            json={'test_case_ids': [case1_id, case2_id]},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        assert resp.get_json()['data']['assigned'] == 2

        # Verify cases are assigned
        case1_detail = client.get(
            f'/api/test-cases/{case1_id}',
            headers=_auth(tenant_data['token_a']),
        ).get_json()['data']
        assert case1_detail['test_project_id'] == project_id

    def test_assign_to_nonexistent_project(self, client, tenant_data):
        resp = client.post(
            '/api/test-projects/99999/assign-cases',
            json={'test_case_ids': [1]},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 7. Update test result -- pass
# ---------------------------------------------------------------------------

class TestUpdateTestResultPass:

    def test_update_test_result_pass(self, client, tenant_data):
        """Update result to pass creates a result record."""
        proj_resp = _create_project(client, tenant_data['token_a'])
        project_id = proj_resp.get_json()['data']['id']

        case_resp = _create_test_case(client, tenant_data['token_a'], title='Pass Case')
        case_id = case_resp.get_json()['data']['id']

        # Assign case
        client.post(
            f'/api/test-projects/{project_id}/assign-cases',
            json={'test_case_ids': [case_id]},
            headers=_auth(tenant_data['token_a']),
        )

        # Update result to pass
        resp = client.put(
            f'/api/test-projects/{project_id}/results',
            json={'test_case_id': case_id, 'status': 'pass'},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['status'] == 'pass'
        assert data['project_id'] == project_id
        assert data['test_case_id'] == case_id


# ---------------------------------------------------------------------------
# 8. Update test result -- fail with notes
# ---------------------------------------------------------------------------

class TestUpdateTestResultFail:

    def test_update_test_result_fail(self, client, tenant_data):
        """Update result to fail includes notes and known_issues."""
        proj_resp = _create_project(client, tenant_data['token_a'])
        project_id = proj_resp.get_json()['data']['id']

        case_resp = _create_test_case(client, tenant_data['token_a'], title='Fail Case')
        case_id = case_resp.get_json()['data']['id']

        client.post(
            f'/api/test-projects/{project_id}/assign-cases',
            json={'test_case_ids': [case_id]},
            headers=_auth(tenant_data['token_a']),
        )

        resp = client.put(
            f'/api/test-projects/{project_id}/results',
            json={
                'test_case_id': case_id,
                'status': 'fail',
                'notes': 'Login button not responding',
                'known_issues': 'JIRA-123',
            },
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['status'] == 'fail'
        assert data['notes'] == 'Login button not responding'
        assert data['known_issues'] == 'JIRA-123'


# ---------------------------------------------------------------------------
# 9. Update test result -- blocked with reason
# ---------------------------------------------------------------------------

class TestUpdateTestResultBlocked:

    def test_update_test_result_blocked(self, client, tenant_data):
        """Blocked result includes blocked_reason."""
        proj_resp = _create_project(client, tenant_data['token_a'])
        project_id = proj_resp.get_json()['data']['id']

        case_resp = _create_test_case(client, tenant_data['token_a'], title='Blocked Case')
        case_id = case_resp.get_json()['data']['id']

        client.post(
            f'/api/test-projects/{project_id}/assign-cases',
            json={'test_case_ids': [case_id]},
            headers=_auth(tenant_data['token_a']),
        )

        resp = client.put(
            f'/api/test-projects/{project_id}/results',
            json={
                'test_case_id': case_id,
                'status': 'blocked',
                'blocked_reason': 'Waiting for API deployment',
            },
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['status'] == 'blocked'
        assert data['blocked_reason'] == 'Waiting for API deployment'


# ---------------------------------------------------------------------------
# 10. Project statistics
# ---------------------------------------------------------------------------

class TestProjectStatistics:

    def test_project_statistics(self, client, tenant_data):
        """Stats calculation counts pass/fail/blocked/not_tested correctly."""
        proj_resp = _create_project(client, tenant_data['token_a'])
        project_id = proj_resp.get_json()['data']['id']

        # Create 4 test cases
        case_ids = []
        for i in range(4):
            resp = _create_test_case(client, tenant_data['token_a'], title=f'Stats Case {i}')
            case_ids.append(resp.get_json()['data']['id'])

        # Assign all cases
        client.post(
            f'/api/test-projects/{project_id}/assign-cases',
            json={'test_case_ids': case_ids},
            headers=_auth(tenant_data['token_a']),
        )

        # Set results: pass, fail, blocked, (not_tested = no result)
        statuses = ['pass', 'fail', 'blocked']
        for i, status in enumerate(statuses):
            client.put(
                f'/api/test-projects/{project_id}/results',
                json={'test_case_id': case_ids[i], 'status': status},
                headers=_auth(tenant_data['token_a']),
            )

        # Get stats
        resp = client.get(
            f'/api/test-projects/{project_id}/stats',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        stats = resp.get_json()['data']

        assert stats['total'] == 4
        assert stats['pass_count'] == 1
        assert stats['fail_count'] == 1
        assert stats['blocked_count'] == 1
        assert stats['not_tested_count'] == 1

    def test_stats_nonexistent_project(self, client, tenant_data):
        resp = client.get(
            '/api/test-projects/99999/stats',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 11. Completion rate
# ---------------------------------------------------------------------------

class TestCompletionRate:

    def test_completion_rate(self, client, tenant_data):
        """Completion rate = (total - not_tested) / total * 100."""
        proj_resp = _create_project(client, tenant_data['token_a'])
        project_id = proj_resp.get_json()['data']['id']

        # Create 5 cases
        case_ids = []
        for i in range(5):
            resp = _create_test_case(client, tenant_data['token_a'], title=f'Rate Case {i}')
            case_ids.append(resp.get_json()['data']['id'])

        # Assign all
        client.post(
            f'/api/test-projects/{project_id}/assign-cases',
            json={'test_case_ids': case_ids},
            headers=_auth(tenant_data['token_a']),
        )

        # Test 4 out of 5 (1 pass, 1 fail, 1 blocked, 1 not_tested explicit)
        # The 5th has no result at all (also not_tested)
        client.put(
            f'/api/test-projects/{project_id}/results',
            json={'test_case_id': case_ids[0], 'status': 'pass'},
            headers=_auth(tenant_data['token_a']),
        )
        client.put(
            f'/api/test-projects/{project_id}/results',
            json={'test_case_id': case_ids[1], 'status': 'fail'},
            headers=_auth(tenant_data['token_a']),
        )
        client.put(
            f'/api/test-projects/{project_id}/results',
            json={'test_case_id': case_ids[2], 'status': 'blocked'},
            headers=_auth(tenant_data['token_a']),
        )

        # Cases 3 and 4 are not tested (no results)
        # Completion rate = (5 - 2) / 5 * 100 = 60.0%
        resp = client.get(
            f'/api/test-projects/{project_id}/stats',
            headers=_auth(tenant_data['token_a']),
        )
        stats = resp.get_json()['data']
        assert stats['total'] == 5
        assert stats['not_tested_count'] == 2
        assert stats['completion_rate'] == 60.0


# ---------------------------------------------------------------------------
# 12. Tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:

    def test_tenant_isolation(self, client, tenant_data):
        """Tenant A cannot see Tenant B's projects."""
        _create_project(client, tenant_data['token_a'], name='A Project')
        _create_project(client, tenant_data['token_b'], name='B Project')

        # Tenant A lists -- should only see their own
        resp_a = client.get('/api/test-projects', headers=_auth(tenant_data['token_a']))
        names_a = [p['name'] for p in resp_a.get_json()['data']]
        assert 'A Project' in names_a
        assert 'B Project' not in names_a

        # Tenant B lists -- should only see their own
        resp_b = client.get('/api/test-projects', headers=_auth(tenant_data['token_b']))
        names_b = [p['name'] for p in resp_b.get_json()['data']]
        assert 'B Project' in names_b
        assert 'A Project' not in names_b

    def test_tenant_a_cannot_get_tenant_b_project(self, client, tenant_data):
        """GET across tenants should return 404."""
        create_resp = _create_project(client, tenant_data['token_b'], name='B Secret')
        project_id = create_resp.get_json()['data']['id']

        resp = client.get(
            f'/api/test-projects/{project_id}',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404

    def test_tenant_a_cannot_update_tenant_b_project(self, client, tenant_data):
        """PUT across tenants should return 404."""
        create_resp = _create_project(client, tenant_data['token_b'], name='B Protected')
        project_id = create_resp.get_json()['data']['id']

        resp = client.put(
            f'/api/test-projects/{project_id}',
            json={'name': 'Hacked!'},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404

    def test_tenant_a_cannot_delete_tenant_b_project(self, client, tenant_data):
        """DELETE across tenants should return 404."""
        create_resp = _create_project(client, tenant_data['token_b'], name='B Delete')
        project_id = create_resp.get_json()['data']['id']

        resp = client.delete(
            f'/api/test-projects/{project_id}',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# UPSERT behavior -- update existing result
# ---------------------------------------------------------------------------

class TestUpsertBehavior:

    def test_upsert_updates_existing_result(self, client, tenant_data):
        """Second PUT to same case updates the existing result, not duplicates."""
        proj_resp = _create_project(client, tenant_data['token_a'])
        project_id = proj_resp.get_json()['data']['id']

        case_resp = _create_test_case(client, tenant_data['token_a'], title='Upsert Case')
        case_id = case_resp.get_json()['data']['id']

        client.post(
            f'/api/test-projects/{project_id}/assign-cases',
            json={'test_case_ids': [case_id]},
            headers=_auth(tenant_data['token_a']),
        )

        # First result: fail
        resp1 = client.put(
            f'/api/test-projects/{project_id}/results',
            json={'test_case_id': case_id, 'status': 'fail', 'notes': 'Bug found'},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp1.status_code == 200
        result_id = resp1.get_json()['data']['id']

        # Second result: pass (UPSERT -- should update, not create new)
        resp2 = client.put(
            f'/api/test-projects/{project_id}/results',
            json={'test_case_id': case_id, 'status': 'pass', 'notes': 'Bug fixed'},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp2.status_code == 200
        data = resp2.get_json()['data']
        assert data['id'] == result_id  # Same result record
        assert data['status'] == 'pass'
        assert data['notes'] == 'Bug fixed'
