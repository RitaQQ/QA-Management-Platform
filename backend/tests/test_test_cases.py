"""
Tests for the test case management and product tag modules.

Covers test case CRUD with separated user_role/feature_description fields,
TC ID auto-increment, filtering, CSV export/import, product tag CRUD,
tag assignment, and tenant isolation.
"""
import io
import pytest
from datetime import datetime, timedelta, timezone

from app_factory import create_app
from database.models import (
    Organization, User, TestCase, TestCaseTag, ProductTag,
    ApiEndpoint, ApiCheckHistory,
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
        db.query(TestCaseTag).delete()
        db.query(TestCase).delete()
        db.query(ProductTag).delete()
        db.query(ApiCheckHistory).delete()
        db.query(ApiEndpoint).delete()
        db.query(User).delete()
        db.query(Organization).delete()
        db.commit()

        # -- Tenant A ---------------------------------------------------------
        org_a = Organization(
            name='TC Org A',
            slug='tc-org-a',
            plan='trial',
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
            subscription_status='trialing',
        )
        db.add(org_a)
        db.flush()

        user_a = User(
            tenant_id=org_a.id,
            username='tc_user_a',
            email='tc_a@test.com',
            password_hash=hash_password('Password123!'),
            role='admin',
        )
        db.add(user_a)
        db.flush()

        # -- Tenant B ---------------------------------------------------------
        org_b = Organization(
            name='TC Org B',
            slug='tc-org-b',
            plan='trial',
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
            subscription_status='trialing',
        )
        db.add(org_b)
        db.flush()

        user_b = User(
            tenant_id=org_b.id,
            username='tc_user_b',
            email='tc_b@test.com',
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
    """Remove all test cases, tags, and associations before each test."""
    db = SessionLocal()
    try:
        db.query(TestCaseTag).delete()
        db.query(TestCase).delete()
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


def _create_case(client, token, **overrides):
    """Helper -- create a test case via the API and return the response."""
    payload = {
        'title': 'Test Login Feature',
        'user_role': 'registered user',
        'feature_description': 'Login using username and password',
        'acceptance_criteria': 'Successful login redirects to dashboard',
        'priority': 'high',
    }
    payload.update(overrides)
    return client.post(
        '/api/test-cases',
        json=payload,
        headers=_auth(token),
    )


def _create_tag(client, token, **overrides):
    """Helper -- create a product tag via the API and return the response."""
    payload = {
        'name': 'Authentication',
        'description': 'Auth-related features',
        'color': '#ff5733',
    }
    payload.update(overrides)
    return client.post(
        '/api/product-tags',
        json=payload,
        headers=_auth(token),
    )


# ---------------------------------------------------------------------------
# 1. Create test case with separated fields
# ---------------------------------------------------------------------------

class TestCreateTestCase:

    def test_create_test_case_with_separated_fields(self, client, tenant_data):
        """user_role and feature_description are independent fields."""
        resp = _create_case(client, tenant_data['token_a'])
        assert resp.status_code == 201
        data = resp.get_json()['data']

        assert data['user_role'] == 'registered user'
        assert data['feature_description'] == 'Login using username and password'
        assert data['acceptance_criteria'] == 'Successful login redirects to dashboard'
        assert data['title'] == 'Test Login Feature'
        assert data['priority'] == 'high'
        assert data['status'] == 'draft'
        assert data['tc_id'].startswith('TC')
        assert 'id' in data

    def test_create_test_case_missing_title(self, client, tenant_data):
        resp = client.post(
            '/api/test-cases',
            json={'user_role': 'admin'},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 400
        assert 'title' in resp.get_json()['error'].lower()

    def test_create_test_case_invalid_priority(self, client, tenant_data):
        resp = _create_case(client, tenant_data['token_a'], priority='critical')
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 2. TC ID auto increment
# ---------------------------------------------------------------------------

class TestTcIdAutoIncrement:

    def test_tc_id_auto_increment(self, client, tenant_data):
        """TC IDs should auto-increment: TC00001, TC00002, etc."""
        resp1 = _create_case(client, tenant_data['token_a'], title='Case 1')
        resp2 = _create_case(client, tenant_data['token_a'], title='Case 2')
        resp3 = _create_case(client, tenant_data['token_a'], title='Case 3')

        assert resp1.get_json()['data']['tc_id'] == 'TC00001'
        assert resp2.get_json()['data']['tc_id'] == 'TC00002'
        assert resp3.get_json()['data']['tc_id'] == 'TC00003'


# ---------------------------------------------------------------------------
# 2b. Custom TC ID
# ---------------------------------------------------------------------------

class TestCustomTcId:

    def test_create_with_custom_tc_id(self, client, tenant_data):
        """User-supplied TC ID is used when provided."""
        resp = _create_case(client, tenant_data['token_a'], title='Custom ID', tc_id='SC001')
        assert resp.status_code == 201
        assert resp.get_json()['data']['tc_id'] == 'SC001'

    def test_create_without_tc_id_auto_generates(self, client, tenant_data):
        """When tc_id is omitted, auto-generate TC00001 format."""
        resp = _create_case(client, tenant_data['token_a'], title='Auto ID')
        assert resp.status_code == 201
        assert resp.get_json()['data']['tc_id'] == 'TC00001'

    def test_create_duplicate_tc_id_rejected(self, client, tenant_data):
        """Duplicate TC ID within the same tenant returns 400."""
        _create_case(client, tenant_data['token_a'], title='First', tc_id='DUP001')
        resp = _create_case(client, tenant_data['token_a'], title='Second', tc_id='DUP001')
        assert resp.status_code == 400
        assert 'DUP001' in resp.get_json()['error']

    def test_same_tc_id_different_tenants_ok(self, client, tenant_data):
        """Same TC ID in different tenants should be allowed."""
        resp_a = _create_case(client, tenant_data['token_a'], title='A', tc_id='CROSS01')
        resp_b = _create_case(client, tenant_data['token_b'], title='B', tc_id='CROSS01')
        assert resp_a.status_code == 201
        assert resp_b.status_code == 201

    def test_update_tc_id_success(self, client, tenant_data):
        """TC ID can be changed via update."""
        create_resp = _create_case(client, tenant_data['token_a'], title='Rename TC')
        case_id = create_resp.get_json()['data']['id']

        resp = client.put(
            f'/api/test-cases/{case_id}',
            json={'tc_id': 'NEW-001'},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        assert resp.get_json()['data']['tc_id'] == 'NEW-001'

    def test_update_tc_id_duplicate_rejected(self, client, tenant_data):
        """Cannot update TC ID to an existing value in the same tenant."""
        _create_case(client, tenant_data['token_a'], title='Existing', tc_id='TAKEN01')
        create_resp = _create_case(client, tenant_data['token_a'], title='Wants TAKEN01')
        case_id = create_resp.get_json()['data']['id']

        resp = client.put(
            f'/api/test-cases/{case_id}',
            json={'tc_id': 'TAKEN01'},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 400
        assert 'TAKEN01' in resp.get_json()['error']

    def test_update_tc_id_same_value_ok(self, client, tenant_data):
        """Updating TC ID to its current value should succeed (no change)."""
        create_resp = _create_case(client, tenant_data['token_a'], title='Same', tc_id='KEEP01')
        case_id = create_resp.get_json()['data']['id']

        resp = client.put(
            f'/api/test-cases/{case_id}',
            json={'tc_id': 'KEEP01'},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        assert resp.get_json()['data']['tc_id'] == 'KEEP01'

    def test_next_tc_id_endpoint(self, client, tenant_data):
        """GET /api/test-cases/next-tc-id returns the next auto ID."""
        resp = client.get('/api/test-cases/next-tc-id', headers=_auth(tenant_data['token_a']))
        assert resp.status_code == 200
        assert resp.get_json()['data'] == 'TC00001'

        # Create one case, next should be TC00002
        _create_case(client, tenant_data['token_a'], title='First')
        resp2 = client.get('/api/test-cases/next-tc-id', headers=_auth(tenant_data['token_a']))
        assert resp2.get_json()['data'] == 'TC00002'

    def test_auto_increment_skips_custom_ids(self, client, tenant_data):
        """Custom TC IDs do not interfere with auto-increment sequence."""
        _create_case(client, tenant_data['token_a'], title='Auto 1')  # TC00001
        _create_case(client, tenant_data['token_a'], title='Custom', tc_id='SC999')
        resp = _create_case(client, tenant_data['token_a'], title='Auto 2')  # should be TC00002
        assert resp.get_json()['data']['tc_id'] == 'TC00002'


# ---------------------------------------------------------------------------
# 2c. CSV import with custom TC ID
# ---------------------------------------------------------------------------

class TestCsvImportCustomTcId:

    def test_csv_import_with_custom_tc_id(self, client, tenant_data):
        """CSV rows with TC ID values use those values."""
        csv_content = (
            'TC ID,Title,User Role,Feature Description,Acceptance Criteria,Priority,Status,Tags\n'
            'LOGIN-01,Login Test,user,Login feature,Can login,high,draft,\n'
        )
        data = io.BytesIO(csv_content.encode('utf-8'))
        resp = client.post(
            '/api/test-cases/import-csv',
            data={'file': (data, 'test.csv')},
            headers=_auth(tenant_data['token_a']),
            content_type='multipart/form-data',
        )
        assert resp.status_code == 200
        result = resp.get_json()['data']
        assert result['created'] == 1

        cases = client.get('/api/test-cases', headers=_auth(tenant_data['token_a'])).get_json()['data']
        assert cases[0]['tc_id'] == 'LOGIN-01'

    def test_csv_import_empty_tc_id_auto_generates(self, client, tenant_data):
        """CSV rows with empty TC ID get auto-generated values."""
        csv_content = (
            'TC ID,Title,User Role,Feature Description,Acceptance Criteria,Priority,Status,Tags\n'
            ',Auto Row,user,desc,criteria,medium,draft,\n'
        )
        data = io.BytesIO(csv_content.encode('utf-8'))
        resp = client.post(
            '/api/test-cases/import-csv',
            data={'file': (data, 'test.csv')},
            headers=_auth(tenant_data['token_a']),
            content_type='multipart/form-data',
        )
        assert resp.status_code == 200
        result = resp.get_json()['data']
        assert result['created'] == 1

        cases = client.get('/api/test-cases', headers=_auth(tenant_data['token_a'])).get_json()['data']
        assert cases[0]['tc_id'].startswith('TC')

    def test_csv_import_duplicate_tc_id_skipped(self, client, tenant_data):
        """CSV row with duplicate TC ID is skipped; rest continue."""
        _create_case(client, tenant_data['token_a'], title='Existing', tc_id='DUP-CSV')
        csv_content = (
            'TC ID,Title,User Role,Feature Description,Acceptance Criteria,Priority,Status,Tags\n'
            'DUP-CSV,Dupe Row,user,desc,criteria,medium,draft,\n'
            'NEW-CSV,New Row,user,desc,criteria,high,draft,\n'
        )
        data = io.BytesIO(csv_content.encode('utf-8'))
        resp = client.post(
            '/api/test-cases/import-csv',
            data={'file': (data, 'test.csv')},
            headers=_auth(tenant_data['token_a']),
            content_type='multipart/form-data',
        )
        assert resp.status_code == 200
        result = resp.get_json()['data']
        assert result['created'] == 1
        assert result['total'] == 2
        assert len(result['errors']) == 1
        assert 'DUP-CSV' in result['errors'][0]


# ---------------------------------------------------------------------------
# 3. List test cases
# ---------------------------------------------------------------------------

class TestListTestCases:

    def test_list_test_cases(self, client, tenant_data):
        """Returns all cases for the tenant."""
        _create_case(client, tenant_data['token_a'], title='Case A1')
        _create_case(client, tenant_data['token_a'], title='Case A2')

        resp = client.get('/api/test-cases', headers=_auth(tenant_data['token_a']))
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert len(data) == 2
        titles = [c['title'] for c in data]
        assert 'Case A1' in titles
        assert 'Case A2' in titles


# ---------------------------------------------------------------------------
# 4. Filter by priority
# ---------------------------------------------------------------------------

class TestFilterByPriority:

    def test_filter_by_priority(self, client, tenant_data):
        """Filter by priority=high returns only high-priority cases."""
        _create_case(client, tenant_data['token_a'], title='High Priority', priority='high')
        _create_case(client, tenant_data['token_a'], title='Low Priority', priority='low')

        resp = client.get(
            '/api/test-cases?priority=high',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert len(data) == 1
        assert data[0]['title'] == 'High Priority'
        assert data[0]['priority'] == 'high'


# ---------------------------------------------------------------------------
# 5. Get test case with tags
# ---------------------------------------------------------------------------

class TestGetTestCaseWithTags:

    def test_get_test_case_with_tags(self, client, tenant_data):
        """Get single case includes associated tags."""
        # Create a tag first
        tag_resp = _create_tag(client, tenant_data['token_a'], name='Login Feature')
        tag_id = tag_resp.get_json()['data']['id']

        # Create case with the tag
        case_resp = _create_case(
            client, tenant_data['token_a'],
            title='Tagged Case',
            tag_ids=[tag_id],
        )
        case_id = case_resp.get_json()['data']['id']

        # Get the case by ID
        resp = client.get(
            f'/api/test-cases/{case_id}',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert len(data['product_tags']) == 1
        assert data['product_tags'][0]['name'] == 'Login Feature'

    def test_get_nonexistent_test_case(self, client, tenant_data):
        resp = client.get(
            '/api/test-cases/99999',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 6. Update test case
# ---------------------------------------------------------------------------

class TestUpdateTestCase:

    def test_update_test_case(self, client, tenant_data):
        """Update fields including user_role and feature_description."""
        create_resp = _create_case(client, tenant_data['token_a'])
        case_id = create_resp.get_json()['data']['id']

        resp = client.put(
            f'/api/test-cases/{case_id}',
            json={
                'title': 'Updated Title',
                'user_role': 'admin user',
                'feature_description': 'Updated description',
                'priority': 'low',
            },
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['title'] == 'Updated Title'
        assert data['user_role'] == 'admin user'
        assert data['feature_description'] == 'Updated description'
        assert data['priority'] == 'low'

    def test_update_nonexistent_test_case(self, client, tenant_data):
        resp = client.put(
            '/api/test-cases/99999',
            json={'title': 'Ghost'},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 7. Delete test case
# ---------------------------------------------------------------------------

class TestDeleteTestCase:

    def test_delete_test_case(self, client, tenant_data):
        """Delete returns 200 and case is gone."""
        create_resp = _create_case(client, tenant_data['token_a'])
        case_id = create_resp.get_json()['data']['id']

        resp = client.delete(
            f'/api/test-cases/{case_id}',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200

        # Verify it is gone
        resp = client.get(
            f'/api/test-cases/{case_id}',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404

    def test_delete_nonexistent_test_case(self, client, tenant_data):
        resp = client.delete(
            '/api/test-cases/99999',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 8. CSV export
# ---------------------------------------------------------------------------

class TestCsvExport:

    def test_csv_export(self, client, tenant_data):
        """Export returns CSV with correct headers and data."""
        _create_case(
            client, tenant_data['token_a'],
            title='Export Test',
            user_role='tester',
            feature_description='Testing export',
            acceptance_criteria='CSV is valid',
            priority='medium',
        )

        resp = client.get(
            '/api/test-cases/export-csv',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        assert 'text/csv' in resp.content_type
        assert 'attachment' in resp.headers.get('Content-Disposition', '')

        csv_text = resp.data.decode('utf-8')
        lines = csv_text.strip().split('\n')
        assert len(lines) >= 2  # header + at least 1 data row

        # Check header
        assert 'TC ID' in lines[0]
        assert 'Title' in lines[0]
        assert 'User Role' in lines[0]
        assert 'Feature Description' in lines[0]

        # Check data row
        assert 'Export Test' in csv_text
        assert 'tester' in csv_text
        assert 'Testing export' in csv_text


# ---------------------------------------------------------------------------
# 9. CSV import
# ---------------------------------------------------------------------------

class TestCsvImport:

    def test_csv_import(self, client, tenant_data):
        """Import creates cases with correct fields."""
        csv_content = (
            'TC ID,Title,User Role,Feature Description,Acceptance Criteria,Priority,Status,Tags\n'
            'TC00001,用戶登入,registered user,使用帳密登入系統,登入成功跳轉首頁,high,draft,"LoginTag"\n'
            'TC00002,用戶登出,admin,點擊登出按鈕,返回登入頁面,medium,ready,\n'
        )

        data = io.BytesIO(csv_content.encode('utf-8'))
        resp = client.post(
            '/api/test-cases/import-csv',
            data={'file': (data, 'test_cases.csv')},
            headers=_auth(tenant_data['token_a']),
            content_type='multipart/form-data',
        )
        assert resp.status_code == 200
        result = resp.get_json()['data']
        assert result['created'] == 2
        assert result['total'] == 2
        assert len(result['errors']) == 0

        # Verify created cases
        list_resp = client.get(
            '/api/test-cases',
            headers=_auth(tenant_data['token_a']),
        )
        cases = list_resp.get_json()['data']
        assert len(cases) == 2
        titles = [c['title'] for c in cases]
        assert '用戶登入' in titles
        assert '用戶登出' in titles

        # Verify the imported case has correct fields
        login_case = next(c for c in cases if c['title'] == '用戶登入')
        assert login_case['user_role'] == 'registered user'
        assert login_case['feature_description'] == '使用帳密登入系統'
        assert login_case['acceptance_criteria'] == '登入成功跳轉首頁'
        assert login_case['priority'] == 'high'

        # Verify tag was created
        assert len(login_case['product_tags']) == 1
        assert login_case['product_tags'][0]['name'] == 'LoginTag'

    def test_csv_import_no_file(self, client, tenant_data):
        resp = client.post(
            '/api/test-cases/import-csv',
            headers=_auth(tenant_data['token_a']),
            content_type='multipart/form-data',
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 10. Product tag CRUD
# ---------------------------------------------------------------------------

class TestProductTagCrud:

    def test_create_product_tag(self, client, tenant_data):
        resp = _create_tag(client, tenant_data['token_a'])
        assert resp.status_code == 201
        data = resp.get_json()['data']
        assert data['name'] == 'Authentication'
        assert data['color'] == '#ff5733'
        assert 'id' in data

    def test_list_product_tags(self, client, tenant_data):
        _create_tag(client, tenant_data['token_a'], name='Tag A')
        _create_tag(client, tenant_data['token_a'], name='Tag B')

        resp = client.get('/api/product-tags', headers=_auth(tenant_data['token_a']))
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert len(data) == 2

    def test_update_product_tag(self, client, tenant_data):
        create_resp = _create_tag(client, tenant_data['token_a'])
        tag_id = create_resp.get_json()['data']['id']

        resp = client.put(
            f'/api/product-tags/{tag_id}',
            json={'name': 'Updated Tag', 'color': '#00ff00'},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['name'] == 'Updated Tag'
        assert data['color'] == '#00ff00'

    def test_delete_product_tag(self, client, tenant_data):
        create_resp = _create_tag(client, tenant_data['token_a'])
        tag_id = create_resp.get_json()['data']['id']

        resp = client.delete(
            f'/api/product-tags/{tag_id}',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200

    def test_create_duplicate_tag_name_rejected(self, client, tenant_data):
        _create_tag(client, tenant_data['token_a'], name='UniqueTag')
        resp = _create_tag(client, tenant_data['token_a'], name='UniqueTag')
        assert resp.status_code == 400
        assert 'already exists' in resp.get_json()['error']


# ---------------------------------------------------------------------------
# 11. Assign tags to case
# ---------------------------------------------------------------------------

class TestAssignTagsToCase:

    def test_assign_tags_to_case(self, client, tenant_data):
        """Assign tags during create and update."""
        # Create two tags
        tag1_resp = _create_tag(client, tenant_data['token_a'], name='Tag1')
        tag2_resp = _create_tag(client, tenant_data['token_a'], name='Tag2')
        tag1_id = tag1_resp.get_json()['data']['id']
        tag2_id = tag2_resp.get_json()['data']['id']

        # Create case with tag1
        case_resp = _create_case(
            client, tenant_data['token_a'],
            title='Tagged Case',
            tag_ids=[tag1_id],
        )
        case_id = case_resp.get_json()['data']['id']
        assert len(case_resp.get_json()['data']['product_tags']) == 1
        assert case_resp.get_json()['data']['product_tags'][0]['name'] == 'Tag1'

        # Update case to have both tags
        update_resp = client.put(
            f'/api/test-cases/{case_id}',
            json={'tag_ids': [tag1_id, tag2_id]},
            headers=_auth(tenant_data['token_a']),
        )
        assert update_resp.status_code == 200
        tags = update_resp.get_json()['data']['product_tags']
        tag_names = [t['name'] for t in tags]
        assert 'Tag1' in tag_names
        assert 'Tag2' in tag_names

        # Update to remove all tags
        update_resp2 = client.put(
            f'/api/test-cases/{case_id}',
            json={'tag_ids': []},
            headers=_auth(tenant_data['token_a']),
        )
        assert update_resp2.status_code == 200
        assert len(update_resp2.get_json()['data']['product_tags']) == 0


# ---------------------------------------------------------------------------
# 12. Tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolationTestCases:

    def test_tenant_isolation(self, client, tenant_data):
        """Tenant A cannot see Tenant B's cases."""
        _create_case(client, tenant_data['token_a'], title='A Only Case')
        _create_case(client, tenant_data['token_b'], title='B Only Case')

        # Tenant A lists -- should only see their own
        resp_a = client.get('/api/test-cases', headers=_auth(tenant_data['token_a']))
        titles_a = [c['title'] for c in resp_a.get_json()['data']]
        assert 'A Only Case' in titles_a
        assert 'B Only Case' not in titles_a

        # Tenant B lists -- should only see their own
        resp_b = client.get('/api/test-cases', headers=_auth(tenant_data['token_b']))
        titles_b = [c['title'] for c in resp_b.get_json()['data']]
        assert 'B Only Case' in titles_b
        assert 'A Only Case' not in titles_b

    def test_tenant_a_cannot_get_tenant_b_case(self, client, tenant_data):
        """GET across tenants should return 404."""
        create_resp = _create_case(client, tenant_data['token_b'], title='Secret B')
        case_id = create_resp.get_json()['data']['id']

        resp = client.get(
            f'/api/test-cases/{case_id}',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404

    def test_tenant_a_cannot_update_tenant_b_case(self, client, tenant_data):
        """PUT across tenants should return 404."""
        create_resp = _create_case(client, tenant_data['token_b'], title='B Protected')
        case_id = create_resp.get_json()['data']['id']

        resp = client.put(
            f'/api/test-cases/{case_id}',
            json={'title': 'Hacked!'},
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404

    def test_tenant_a_cannot_delete_tenant_b_case(self, client, tenant_data):
        """DELETE across tenants should return 404."""
        create_resp = _create_case(client, tenant_data['token_b'], title='B Delete')
        case_id = create_resp.get_json()['data']['id']

        resp = client.delete(
            f'/api/test-cases/{case_id}',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404

    def test_product_tag_tenant_isolation(self, client, tenant_data):
        """Tenant A cannot see Tenant B's tags."""
        _create_tag(client, tenant_data['token_a'], name='A Tag')
        _create_tag(client, tenant_data['token_b'], name='B Tag')

        resp_a = client.get('/api/product-tags', headers=_auth(tenant_data['token_a']))
        names_a = [t['name'] for t in resp_a.get_json()['data']]
        assert 'A Tag' in names_a
        assert 'B Tag' not in names_a
