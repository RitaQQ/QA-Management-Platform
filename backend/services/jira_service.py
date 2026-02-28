"""
Jira integration service -- API Token authentication, issue creation, and bidirectional sync.

Provides functions for:
- API Token based connection to Jira Cloud
- Creating Jira issues from failed test results
- Handling Jira webhooks for bidirectional status sync
- Manual issue status synchronization
- Querying Jira issue links for test projects

All tenant-scoped operations use ``get_tenant_id()`` from :mod:`middleware.tenant`.
"""
import base64
import logging
from datetime import datetime, timezone

import requests

from database.models import Organization, JiraIssueLink, TestCase, TestResult, TestProject
from middleware.tenant import tenant_filter, set_tenant_fields, get_tenant_id

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# API Token connection management
# ---------------------------------------------------------------------------

def connect_with_token(db, site_url, email, api_token):
    """Store Jira API Token credentials for the current tenant.

    Normalises the site URL (strips trailing slash, prepends https:// if missing),
    clears any legacy OAuth fields, and persists the new credentials.

    Returns
    -------
    tuple
        ``(result_dict, error_string)``
    """
    if not site_url or not email or not api_token:
        return None, 'site_url, email, and api_token are required'

    # Normalise URL
    site_url = site_url.strip().rstrip('/')
    if not site_url.startswith('http://') and not site_url.startswith('https://'):
        site_url = f'https://{site_url}'

    tenant_id = get_tenant_id()
    org = db.query(Organization).filter_by(id=tenant_id).first()
    if not org:
        return None, 'Organization not found'

    org.jira_site_url = site_url
    org.jira_user_email = email.strip()
    org.jira_api_token = api_token

    # Clear legacy OAuth fields
    org.jira_access_token = None
    org.jira_refresh_token = None
    org.jira_token_expires_at = None
    org.jira_cloud_id = None

    db.commit()
    return {'connected': True, 'site_url': org.jira_site_url, 'user_email': org.jira_user_email}, None


def test_connection(db):
    """Test that the stored Jira credentials are valid.

    Calls ``GET /rest/api/3/myself`` and returns the authenticated user's
    display name on success.

    Returns
    -------
    tuple
        ``(result_dict, error_string)``
    """
    headers, err = _get_jira_headers(db)
    if err:
        return None, err
    base_url, err = _get_jira_base_url(db)
    if err:
        return None, err

    try:
        resp = requests.get(f'{base_url}/myself', headers=headers, timeout=10)
    except requests.ConnectionError:
        return None, 'Cannot connect to Jira site'
    except requests.Timeout:
        return None, 'Connection to Jira timed out'

    if resp.status_code == 401:
        return None, 'Invalid credentials'
    if resp.status_code != 200:
        return None, f'Jira API error: {resp.status_code}'

    data = resp.json()
    return {'ok': True, 'display_name': data.get('displayName', '')}, None


def disconnect(db):
    """Clear all Jira credentials for the current tenant.

    Returns
    -------
    tuple
        ``(result_dict, error_string)``
    """
    tenant_id = get_tenant_id()
    org = db.query(Organization).filter_by(id=tenant_id).first()
    if not org:
        return None, 'Organization not found'

    org.jira_site_url = None
    org.jira_user_email = None
    org.jira_api_token = None
    org.jira_access_token = None
    org.jira_refresh_token = None
    org.jira_token_expires_at = None
    org.jira_cloud_id = None

    db.commit()
    return {'connected': False}, None


def get_connection_status(db):
    """Check whether Jira is connected for the current tenant.

    Returns
    -------
    dict
        ``{'connected': bool, 'site_url': str|None, 'user_email': str|None}``
    """
    tenant_id = get_tenant_id()
    org = db.query(Organization).filter_by(id=tenant_id).first()
    if not org:
        return {'connected': False, 'site_url': None, 'user_email': None}

    connected = bool(org.jira_api_token and org.jira_user_email and org.jira_site_url)
    return {
        'connected': connected,
        'site_url': org.jira_site_url if connected else None,
        'user_email': org.jira_user_email if connected else None,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_jira_headers(db):
    """Build authorization headers for Jira API calls using Basic auth.

    Returns
    -------
    tuple
        ``(headers_dict, error_string)``
    """
    org = db.query(Organization).filter_by(id=get_tenant_id()).first()
    if not org or not org.jira_api_token or not org.jira_user_email:
        return None, 'Jira not connected'
    credentials = base64.b64encode(
        f'{org.jira_user_email}:{org.jira_api_token}'.encode()
    ).decode()
    return {
        'Authorization': f'Basic {credentials}',
        'Content-Type': 'application/json',
    }, None


def _get_jira_base_url(db):
    """Get the REST API v3 base URL for the current tenant's Jira Cloud site.

    Returns
    -------
    tuple
        ``(base_url_string, error_string)``
    """
    org = db.query(Organization).filter_by(id=get_tenant_id()).first()
    if not org or not org.jira_site_url:
        return None, 'Jira not connected'
    return f'{org.jira_site_url}/rest/api/3', None


# ---------------------------------------------------------------------------
# Jira project listing
# ---------------------------------------------------------------------------

def list_projects(db):
    """List available Jira projects for the connected site.

    Returns
    -------
    tuple
        ``(list_of_project_dicts, error_string)``
    """
    base_url, err = _get_jira_base_url(db)
    if err:
        return None, err
    headers, err = _get_jira_headers(db)
    if err:
        return None, err

    resp = requests.get(f'{base_url}/project', headers=headers)
    if resp.status_code != 200:
        return None, f'Jira API error: {resp.status_code}'

    projects = [
        {'key': p['key'], 'name': p['name'], 'id': p['id']}
        for p in resp.json()
    ]
    return projects, None


# ---------------------------------------------------------------------------
# Issue creation from failed test result
# ---------------------------------------------------------------------------

def create_issue_from_test_result(db, test_result_id, project_key, issue_type='Bug'):
    """Create a Jira issue from a failed test result.

    Builds a description from the associated test case details and creates
    the issue in the specified Jira project.  A :class:`JiraIssueLink` record
    is persisted to track the relationship.

    Parameters
    ----------
    db : Session
        Database session.
    test_result_id : int
        ID of the :class:`TestResult` to create an issue for.
    project_key : str
        Jira project key (e.g. ``'PROJ'``).
    issue_type : str
        Jira issue type name (default ``'Bug'``).

    Returns
    -------
    tuple
        ``(result_dict, error_string)``
    """
    base_url, err = _get_jira_base_url(db)
    if err:
        return None, err
    headers, err = _get_jira_headers(db)
    if err:
        return None, err

    # Look up test result (tenant-scoped via TestResult.tenant_id)
    result = (
        db.query(TestResult)
        .filter_by(id=test_result_id, tenant_id=get_tenant_id())
        .first()
    )
    if not result:
        return None, 'Test result not found'

    case = tenant_filter(db.query(TestCase), TestCase).filter_by(id=result.test_case_id).first()
    if not case:
        return None, 'Test case not found'

    # Build a human-readable description
    desc_parts = [f"Test Case: {case.tc_id} - {case.title}"]
    if case.user_role:
        desc_parts.append(f"User Role: {case.user_role}")
    if case.feature_description:
        desc_parts.append(f"Feature: {case.feature_description}")
    if case.acceptance_criteria:
        desc_parts.append(f"Acceptance Criteria: {case.acceptance_criteria}")
    if result.notes:
        desc_parts.append(f"\nTest Notes: {result.notes}")
    if result.known_issues:
        desc_parts.append(f"Known Issues: {result.known_issues}")
    description_text = '\n'.join(desc_parts)

    # Jira REST API v3 uses Atlassian Document Format for description
    payload = {
        'fields': {
            'project': {'key': project_key},
            'summary': f"[{case.tc_id}] {case.title} - Test Failed",
            'description': {
                'type': 'doc',
                'version': 1,
                'content': [{
                    'type': 'paragraph',
                    'content': [{'type': 'text', 'text': description_text}],
                }],
            },
            'issuetype': {'name': issue_type},
        }
    }

    resp = requests.post(f'{base_url}/issue', headers=headers, json=payload)
    if resp.status_code not in (200, 201):
        return None, f'Failed to create Jira issue: {resp.text}'

    issue_data = resp.json()

    # Persist the link
    link = JiraIssueLink(
        test_case_id=case.id,
        test_result_id=result.id,
        jira_issue_key=issue_data['key'],
        jira_issue_summary=f"[{case.tc_id}] {case.title} - Test Failed",
        jira_status='Open',
        last_synced_at=datetime.now(timezone.utc),
    )
    set_tenant_fields(link)
    db.add(link)
    db.commit()

    org = db.query(Organization).filter_by(id=get_tenant_id()).first()
    return {
        'jira_issue_key': issue_data['key'],
        'jira_issue_url': f"{org.jira_site_url}/browse/{issue_data['key']}",
        'link_id': link.id,
    }, None


# ---------------------------------------------------------------------------
# Webhook handler
# ---------------------------------------------------------------------------

def handle_webhook(db, payload):
    """Handle a Jira webhook callback for issue status changes.

    Only ``jira:issue_updated`` events are processed.  All matching
    :class:`JiraIssueLink` records are updated with the latest status,
    assignee, priority, and summary from the payload.

    Parameters
    ----------
    db : Session
        Database session.
    payload : dict
        The JSON body sent by Jira's webhook.

    Returns
    -------
    tuple
        ``(result_dict, error_string)``
    """
    event = payload.get('webhookEvent', '')
    if event != 'jira:issue_updated':
        return {'ignored': True}, None

    issue = payload.get('issue', {})
    issue_key = issue.get('key')
    if not issue_key:
        return {'ignored': True}, None

    status = issue.get('fields', {}).get('status', {}).get('name', '')
    assignee_field = issue.get('fields', {}).get('assignee')
    assignee_name = assignee_field.get('displayName', '') if assignee_field else ''
    priority_field = issue.get('fields', {}).get('priority')
    priority_name = priority_field.get('name', '') if priority_field else ''
    summary = issue.get('fields', {}).get('summary', '')

    # Update all matching links (across all tenants -- webhook is global)
    links = db.query(JiraIssueLink).filter_by(jira_issue_key=issue_key).all()
    updated = 0
    for link in links:
        link.jira_status = status
        link.jira_assignee = assignee_name
        link.jira_priority = priority_name
        link.jira_issue_summary = summary
        link.last_synced_at = datetime.now(timezone.utc)
        updated += 1

    db.commit()
    return {'updated': updated, 'issue_key': issue_key, 'new_status': status}, None


# ---------------------------------------------------------------------------
# Manual sync
# ---------------------------------------------------------------------------

def sync_issue_status(db, link_id):
    """Manually synchronize the status of a single Jira issue link.

    Fetches the current issue data from Jira and updates the local
    :class:`JiraIssueLink` record.

    Returns
    -------
    tuple
        ``(result_dict, error_string)``
    """
    link = (
        db.query(JiraIssueLink)
        .filter_by(id=link_id, tenant_id=get_tenant_id())
        .first()
    )
    if not link:
        return None, 'Link not found'

    base_url, err = _get_jira_base_url(db)
    if err:
        return None, err
    headers, err = _get_jira_headers(db)
    if err:
        return None, err

    resp = requests.get(f'{base_url}/issue/{link.jira_issue_key}', headers=headers)
    if resp.status_code != 200:
        return None, f'Failed to fetch issue: {resp.status_code}'

    issue = resp.json()
    link.jira_status = issue['fields']['status']['name']

    assignee = issue['fields'].get('assignee')
    link.jira_assignee = assignee['displayName'] if assignee else ''

    priority = issue['fields'].get('priority')
    link.jira_priority = priority['name'] if priority else ''

    link.jira_issue_summary = issue['fields']['summary']
    link.last_synced_at = datetime.now(timezone.utc)
    db.commit()

    return {
        'jira_issue_key': link.jira_issue_key,
        'jira_status': link.jira_status,
        'jira_assignee': link.jira_assignee,
        'last_synced_at': link.last_synced_at.isoformat(),
    }, None


# ---------------------------------------------------------------------------
# Issue links for a test project
# ---------------------------------------------------------------------------

def get_issue_links_for_project(db, project_id):
    """Get all Jira issue links associated with a test project.

    Joins through :class:`TestResult` to find links whose test results
    belong to the specified project.

    Returns
    -------
    tuple
        ``(list_of_link_dicts, error_string)``
    """
    project = (
        tenant_filter(db.query(TestProject), TestProject)
        .filter_by(id=project_id)
        .first()
    )
    if not project:
        return None, 'Project not found'

    links = (
        db.query(JiraIssueLink)
        .join(TestResult, JiraIssueLink.test_result_id == TestResult.id)
        .filter(
            TestResult.project_id == project_id,
            JiraIssueLink.tenant_id == get_tenant_id(),
        )
        .all()
    )

    return [
        {
            'id': link.id,
            'test_case_id': link.test_case_id,
            'test_result_id': link.test_result_id,
            'jira_issue_key': link.jira_issue_key,
            'jira_issue_summary': link.jira_issue_summary,
            'jira_status': link.jira_status,
            'jira_assignee': link.jira_assignee,
            'jira_priority': link.jira_priority,
            'last_synced_at': link.last_synced_at.isoformat() if link.last_synced_at else None,
        }
        for link in links
    ], None
