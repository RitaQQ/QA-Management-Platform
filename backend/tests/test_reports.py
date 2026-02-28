"""
Tests for the report generation module.

Covers JSON report structure, statistics calculation, Jira bug summary,
PDF generation, error handling, and tenant isolation.
"""
import pytest
from datetime import datetime, timedelta, timezone

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
    """Create two tenants with users, projects, test cases, results, and Jira links.

    Tenant A has:
    - 1 project with 4 test cases
    - Results: 2 pass, 1 fail, 1 not_tested (no result row)
    - 3 Jira issue links on the fail result

    Tenant B has:
    - 1 project with 1 test case (used for isolation tests)
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
            name='Report Org A',
            slug='report-org-a',
            plan='trial',
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
            subscription_status='trialing',
        )
        db.add(org_a)
        db.flush()

        user_a = User(
            tenant_id=org_a.id,
            username='report_user_a',
            email='report_a@test.com',
            password_hash=hash_password('Password123!'),
            role='admin',
        )
        db.add(user_a)
        db.flush()

        project_a = TestProject(
            tenant_id=org_a.id,
            name='Report Project A',
            description='Project for report testing',
            status='in_progress',
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2026, 3, 1, tzinfo=timezone.utc),
        )
        db.add(project_a)
        db.flush()

        # 4 test cases assigned to project A
        case_a1 = TestCase(
            tenant_id=org_a.id,
            tc_id='TC00001',
            title='Login Test',
            user_role='Admin',
            feature_description='User login with password',
            priority='high',
            status='ready',
            test_project_id=project_a.id,
        )
        case_a2 = TestCase(
            tenant_id=org_a.id,
            tc_id='TC00002',
            title='Signup Test',
            user_role='User',
            feature_description='New user registration',
            priority='medium',
            status='ready',
            test_project_id=project_a.id,
        )
        case_a3 = TestCase(
            tenant_id=org_a.id,
            tc_id='TC00003',
            title='Password Reset Test',
            user_role='User',
            feature_description='Password reset via email',
            priority='high',
            status='ready',
            test_project_id=project_a.id,
        )
        case_a4 = TestCase(
            tenant_id=org_a.id,
            tc_id='TC00004',
            title='Logout Test',
            user_role='Admin',
            feature_description='User logout functionality',
            priority='low',
            status='draft',
            test_project_id=project_a.id,
        )
        db.add_all([case_a1, case_a2, case_a3, case_a4])
        db.flush()

        # Results: pass, pass, fail, (no result for case_a4 = not_tested)
        result_a1 = TestResult(
            tenant_id=org_a.id,
            project_id=project_a.id,
            test_case_id=case_a1.id,
            status='pass',
            notes='Login works correctly',
        )
        result_a2 = TestResult(
            tenant_id=org_a.id,
            project_id=project_a.id,
            test_case_id=case_a2.id,
            status='pass',
            notes='Registration flow OK',
        )
        result_a3 = TestResult(
            tenant_id=org_a.id,
            project_id=project_a.id,
            test_case_id=case_a3.id,
            status='fail',
            notes='Email not sent',
            known_issues='SMTP config missing',
            blocked_reason=None,
        )
        db.add_all([result_a1, result_a2, result_a3])
        db.flush()

        # Jira links on the fail result (3 bugs: 1 open, 1 in progress, 1 done)
        jira_link_1 = JiraIssueLink(
            tenant_id=org_a.id,
            test_case_id=case_a3.id,
            test_result_id=result_a3.id,
            jira_issue_key='PROJ-101',
            jira_issue_summary='SMTP config bug',
            jira_status='Open',
            jira_assignee='Alice',
            jira_priority='High',
            last_synced_at=datetime.now(timezone.utc),
        )
        jira_link_2 = JiraIssueLink(
            tenant_id=org_a.id,
            test_case_id=case_a3.id,
            test_result_id=result_a3.id,
            jira_issue_key='PROJ-102',
            jira_issue_summary='Email template issue',
            jira_status='In Progress',
            jira_assignee='Bob',
            jira_priority='Medium',
            last_synced_at=datetime.now(timezone.utc),
        )
        jira_link_3 = JiraIssueLink(
            tenant_id=org_a.id,
            test_case_id=case_a3.id,
            test_result_id=result_a3.id,
            jira_issue_key='PROJ-103',
            jira_issue_summary='Fixed email bug',
            jira_status='Done',
            jira_assignee='Charlie',
            jira_priority='Low',
            last_synced_at=datetime.now(timezone.utc),
        )
        db.add_all([jira_link_1, jira_link_2, jira_link_3])
        db.flush()

        # -- Tenant B ---------------------------------------------------------
        org_b = Organization(
            name='Report Org B',
            slug='report-org-b',
            plan='trial',
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
            subscription_status='trialing',
        )
        db.add(org_b)
        db.flush()

        user_b = User(
            tenant_id=org_b.id,
            username='report_user_b',
            email='report_b@test.com',
            password_hash=hash_password('Password123!'),
            role='admin',
        )
        db.add(user_b)
        db.flush()

        project_b = TestProject(
            tenant_id=org_b.id,
            name='Report Project B',
            description='Tenant B project',
            status='draft',
        )
        db.add(project_b)
        db.flush()

        case_b1 = TestCase(
            tenant_id=org_b.id,
            tc_id='TC00001',
            title='Tenant B Only Test',
            priority='medium',
            status='ready',
            test_project_id=project_b.id,
        )
        db.add(case_b1)
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
            'case_a1_id': case_a1.id,
            'case_a2_id': case_a2.id,
            'case_a3_id': case_a3.id,
            'case_a4_id': case_a4.id,
            'result_a3_id': result_a3.id,
        }
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
# 1. test_json_report_includes_stats
# ---------------------------------------------------------------------------

class TestJsonReportIncludesStats:

    def test_json_report_includes_stats(self, client, tenant_data):
        """JSON report contains stats with all required fields."""
        resp = client.get(
            f'/api/test-projects/{tenant_data["project_a_id"]}/report',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']

        assert 'stats' in data
        stats = data['stats']
        assert 'total' in stats
        assert 'pass_count' in stats
        assert 'fail_count' in stats
        assert 'blocked_count' in stats
        assert 'not_tested_count' in stats
        assert 'completion_rate' in stats

        # Verify actual values
        assert stats['total'] == 4
        assert stats['pass_count'] == 2
        assert stats['fail_count'] == 1
        assert stats['not_tested_count'] == 1


# ---------------------------------------------------------------------------
# 2. test_json_report_includes_jira_summary
# ---------------------------------------------------------------------------

class TestJsonReportIncludesJiraSummary:

    def test_json_report_includes_jira_summary(self, client, tenant_data):
        """JSON report contains jira_summary with open/in_progress/resolved counts."""
        resp = client.get(
            f'/api/test-projects/{tenant_data["project_a_id"]}/report',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']

        assert 'jira_summary' in data
        jira = data['jira_summary']
        assert 'open_count' in jira
        assert 'in_progress_count' in jira
        assert 'resolved_count' in jira
        assert 'total' in jira

        # Verify counts: 1 Open, 1 In Progress, 1 Done (resolved)
        assert jira['open_count'] == 1
        assert jira['in_progress_count'] == 1
        assert jira['resolved_count'] == 1
        assert jira['total'] == 3


# ---------------------------------------------------------------------------
# 3. test_json_report_includes_case_details
# ---------------------------------------------------------------------------

class TestJsonReportIncludesCaseDetails:

    def test_json_report_includes_case_details(self, client, tenant_data):
        """Each test case in the report has result_status and jira_issues."""
        resp = client.get(
            f'/api/test-projects/{tenant_data["project_a_id"]}/report',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']

        assert 'test_cases' in data
        cases = data['test_cases']
        assert len(cases) == 4

        # All cases have required fields
        for case in cases:
            assert 'tc_id' in case
            assert 'title' in case
            assert 'result_status' in case
            assert 'jira_issues' in case

        # Find the failed case (TC00003) and check its Jira issues
        failed_case = next(c for c in cases if c['tc_id'] == 'TC00003')
        assert failed_case['result_status'] == 'fail'
        assert len(failed_case['jira_issues']) == 3

        jira_keys = {j['key'] for j in failed_case['jira_issues']}
        assert jira_keys == {'PROJ-101', 'PROJ-102', 'PROJ-103'}

        # Check each Jira issue has the expected fields
        for jira_issue in failed_case['jira_issues']:
            assert 'key' in jira_issue
            assert 'summary' in jira_issue
            assert 'status' in jira_issue
            assert 'assignee' in jira_issue
            assert 'priority' in jira_issue


# ---------------------------------------------------------------------------
# 4. test_json_report_completion_rate
# ---------------------------------------------------------------------------

class TestJsonReportCompletionRate:

    def test_json_report_completion_rate(self, client, tenant_data):
        """Completion rate is calculated correctly.

        4 total cases: 2 pass + 1 fail + 1 not_tested
        Completion = (4 - 1) / 4 * 100 = 75.0%
        """
        resp = client.get(
            f'/api/test-projects/{tenant_data["project_a_id"]}/report',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        stats = resp.get_json()['data']['stats']
        assert stats['completion_rate'] == 75.0


# ---------------------------------------------------------------------------
# 5. test_pdf_report_returns_pdf
# ---------------------------------------------------------------------------

class TestPdfReportReturnsPdf:

    def test_pdf_report_returns_pdf(self, client, tenant_data):
        """PDF report returns content-type application/pdf."""
        resp = client.get(
            f'/api/test-projects/{tenant_data["project_a_id"]}/report?format=pdf',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        assert resp.content_type == 'application/pdf'
        assert 'attachment' in resp.headers.get('Content-Disposition', '')
        assert f'report-{tenant_data["project_a_id"]}.pdf' in resp.headers.get('Content-Disposition', '')


# ---------------------------------------------------------------------------
# 6. test_pdf_report_not_empty
# ---------------------------------------------------------------------------

class TestPdfReportNotEmpty:

    def test_pdf_report_not_empty(self, client, tenant_data):
        """PDF report has substantial content (> 1000 bytes)."""
        resp = client.get(
            f'/api/test-projects/{tenant_data["project_a_id"]}/report?format=pdf',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        assert len(resp.data) > 1000

        # Verify it starts with PDF magic bytes
        assert resp.data[:5] == b'%PDF-'


# ---------------------------------------------------------------------------
# 7. test_report_project_not_found
# ---------------------------------------------------------------------------

class TestReportProjectNotFound:

    def test_report_project_not_found(self, client, tenant_data):
        """Returns 404 for an invalid project ID."""
        resp = client.get(
            '/api/test-projects/99999/report',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 404
        assert 'not found' in resp.get_json()['error'].lower()


# ---------------------------------------------------------------------------
# 8. test_tenant_isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:

    def test_tenant_isolation(self, client, tenant_data):
        """Tenant B cannot generate a report for Tenant A's project."""
        resp = client.get(
            f'/api/test-projects/{tenant_data["project_a_id"]}/report',
            headers=_auth(tenant_data['token_b']),
        )
        assert resp.status_code == 404
        assert 'not found' in resp.get_json()['error'].lower()

    def test_tenant_b_can_access_own_project_report(self, client, tenant_data):
        """Tenant B can generate a report for its own project."""
        resp = client.get(
            f'/api/test-projects/{tenant_data["project_b_id"]}/report',
            headers=_auth(tenant_data['token_b']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['project']['name'] == 'Report Project B'

    def test_requires_auth(self, client, tenant_data):
        """Report endpoint requires authentication."""
        resp = client.get(
            f'/api/test-projects/{tenant_data["project_a_id"]}/report',
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Additional edge case tests
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_report_includes_project_metadata(self, client, tenant_data):
        """Report includes project name, description, status, and timestamps."""
        resp = client.get(
            f'/api/test-projects/{tenant_data["project_a_id"]}/report',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        project = resp.get_json()['data']['project']
        assert project['name'] == 'Report Project A'
        assert project['description'] == 'Project for report testing'
        assert project['status'] == 'in_progress'
        assert project['start_time'] is not None
        assert project['end_time'] is not None

    def test_report_includes_generated_at(self, client, tenant_data):
        """Report includes a generated_at timestamp."""
        resp = client.get(
            f'/api/test-projects/{tenant_data["project_a_id"]}/report',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert 'generated_at' in data
        assert data['generated_at'] is not None

    def test_invalid_format_returns_400(self, client, tenant_data):
        """Requesting an invalid format returns 400."""
        resp = client.get(
            f'/api/test-projects/{tenant_data["project_a_id"]}/report?format=xml',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 400
        assert 'Invalid format' in resp.get_json()['error']

    def test_not_tested_case_has_null_fields(self, client, tenant_data):
        """A case with no test result should have null notes/blocked_reason."""
        resp = client.get(
            f'/api/test-projects/{tenant_data["project_a_id"]}/report',
            headers=_auth(tenant_data['token_a']),
        )
        assert resp.status_code == 200
        cases = resp.get_json()['data']['test_cases']
        not_tested_case = next(c for c in cases if c['tc_id'] == 'TC00004')
        assert not_tested_case['result_status'] == 'not_tested'
        assert not_tested_case['notes'] is None
        assert not_tested_case['blocked_reason'] is None
        assert not_tested_case['jira_issues'] == []
