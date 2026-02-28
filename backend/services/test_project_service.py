"""
Test project service -- CRUD, test case assignment, result tracking, and statistics.

All database queries are scoped to the current tenant via ``tenant_filter``
and ``set_tenant_fields`` from :mod:`middleware.tenant`.
"""
import logging
from datetime import datetime, timezone

from database.models import TestProject, TestCase, TestResult, User
from middleware.tenant import tenant_filter, set_tenant_fields

logger = logging.getLogger(__name__)

# Valid values for validation
VALID_STATUSES = ('draft', 'in_progress', 'completed')
VALID_RESULT_STATUSES = ('pass', 'fail', 'blocked', 'not_tested')


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def _project_to_dict(project, db=None, include_cases=False):
    """Serialize a :class:`TestProject` ORM instance to a plain dict.

    When *db* is provided, includes summary stats. When *include_cases*
    is True, includes the assigned test cases with their results.
    """
    result = {
        'id': project.id,
        'name': project.name,
        'description': project.description,
        'status': project.status,
        'responsible_user_id': str(project.responsible_user_id) if project.responsible_user_id else None,
        'responsible_user_name': None,
        'start_time': project.start_time.isoformat() if project.start_time else None,
        'end_time': project.end_time.isoformat() if project.end_time else None,
        'created_at': project.created_at.isoformat() if project.created_at else None,
        'updated_at': project.updated_at.isoformat() if project.updated_at else None,
    }

    # Resolve responsible user name
    if db and project.responsible_user_id:
        user = db.query(User).filter_by(id=project.responsible_user_id).first()
        if user:
            result['responsible_user_name'] = user.username

    # Include stats
    if db:
        result['stats'] = _compute_stats(db, project.id)

    # Include test cases and their results
    if db and include_cases:
        result['test_cases'] = _get_project_cases_with_results(db, project)

    return result


def _result_to_dict(result):
    """Serialize a :class:`TestResult` ORM instance to a plain dict."""
    return {
        'id': result.id,
        'project_id': result.project_id,
        'test_case_id': result.test_case_id,
        'status': result.status,
        'notes': result.notes,
        'known_issues': result.known_issues,
        'blocked_reason': result.blocked_reason,
        'tested_at': result.tested_at.isoformat() if result.tested_at else None,
        'created_at': result.created_at.isoformat() if result.created_at else None,
        'updated_at': result.updated_at.isoformat() if result.updated_at else None,
    }


def _compute_stats(db, project_id):
    """Calculate pass/fail/blocked/not_tested counts for a project.

    Counts all test cases assigned to the project (via test_project_id).
    For each assigned case, checks if a TestResult exists; cases without
    a result are counted as not_tested.
    """
    # Get all test cases assigned to this project
    assigned_cases = (
        tenant_filter(db.query(TestCase), TestCase)
        .filter(TestCase.test_project_id == project_id)
        .all()
    )
    total = len(assigned_cases)
    if total == 0:
        return {
            'total': 0,
            'pass_count': 0,
            'fail_count': 0,
            'blocked_count': 0,
            'not_tested_count': 0,
            'completion_rate': 0.0,
        }

    # Get results for these cases
    case_ids = [c.id for c in assigned_cases]
    results = (
        db.query(TestResult)
        .filter(
            TestResult.project_id == project_id,
            TestResult.test_case_id.in_(case_ids),
        )
        .all()
    )

    # Build a status map
    result_map = {r.test_case_id: r.status for r in results}

    pass_count = sum(1 for s in result_map.values() if s == 'pass')
    fail_count = sum(1 for s in result_map.values() if s == 'fail')
    blocked_count = sum(1 for s in result_map.values() if s == 'blocked')
    # Cases without a result + results with not_tested status
    not_tested_from_results = sum(1 for s in result_map.values() if s == 'not_tested')
    cases_without_result = total - len(result_map)
    not_tested_count = not_tested_from_results + cases_without_result

    completion_rate = ((total - not_tested_count) / total * 100) if total > 0 else 0.0

    return {
        'total': total,
        'pass_count': pass_count,
        'fail_count': fail_count,
        'blocked_count': blocked_count,
        'not_tested_count': not_tested_count,
        'completion_rate': round(completion_rate, 1),
    }


def _get_project_cases_with_results(db, project):
    """Return assigned test cases with their test results for the project."""
    cases = (
        tenant_filter(db.query(TestCase), TestCase)
        .filter(TestCase.test_project_id == project.id)
        .order_by(TestCase.id.asc())
        .all()
    )

    # Batch-load user names for assigned users to avoid N+1
    user_ids = {case.responsible_user_id for case in cases if case.responsible_user_id}
    user_map = {}
    if user_ids:
        users = db.query(User).filter(User.id.in_(user_ids)).all()
        user_map = {u.id: u.username for u in users}

    case_list = []
    for case in cases:
        result = (
            db.query(TestResult)
            .filter_by(project_id=project.id, test_case_id=case.id)
            .first()
        )
        case_dict = {
            'id': case.id,
            'tc_id': case.tc_id,
            'title': case.title,
            'priority': case.priority,
            'status': case.status,
            'assigned_user_id': str(case.responsible_user_id) if case.responsible_user_id else None,
            'assigned_user_name': user_map.get(case.responsible_user_id) if case.responsible_user_id else None,
            'result': _result_to_dict(result) if result else None,
        }
        case_list.append(case_dict)

    return case_list


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def list_projects(db):
    """Return all projects for the current tenant with summary stats."""
    projects = (
        tenant_filter(db.query(TestProject), TestProject)
        .order_by(TestProject.id.asc())
        .all()
    )
    return [_project_to_dict(p, db) for p in projects]


def get_project(db, project_id):
    """Return a single project dict with test cases and results, or ``None``."""
    project = (
        tenant_filter(db.query(TestProject), TestProject)
        .filter_by(id=project_id)
        .first()
    )
    if not project:
        return None
    return _project_to_dict(project, db, include_cases=True)


def create_project(db, data):
    """Create a new test project.

    Returns ``(project_dict, None)`` on success or ``(None, error)`` on failure.
    Required field: ``name``.
    """
    if not data.get('name'):
        return None, 'name is required'

    status = data.get('status', 'draft')
    if status not in VALID_STATUSES:
        return None, f'Invalid status: {status}'

    # Check for duplicate name within tenant
    existing = (
        tenant_filter(db.query(TestProject), TestProject)
        .filter_by(name=data['name'])
        .first()
    )
    if existing:
        return None, 'Project name already exists'

    project = TestProject(
        name=data['name'],
        description=data.get('description'),
        status=status,
        responsible_user_id=data.get('responsible_user_id'),
        start_time=_parse_datetime(data.get('start_time')),
        end_time=_parse_datetime(data.get('end_time')),
    )
    set_tenant_fields(project)
    db.add(project)
    db.flush()

    # Optionally assign test cases during creation
    test_case_ids = data.get('test_case_ids', [])
    if test_case_ids:
        _assign_cases_to_project(db, project.id, test_case_ids)

    db.commit()
    db.refresh(project)
    return _project_to_dict(project, db), None


def update_project(db, project_id, data):
    """Update an existing test project.

    Returns ``(project_dict, None)`` on success, ``(None, 'Not found')`` if missing,
    or ``(None, error_message)`` on validation failure.
    """
    project = (
        tenant_filter(db.query(TestProject), TestProject)
        .filter_by(id=project_id)
        .first()
    )
    if not project:
        return None, 'Not found'

    if 'name' in data:
        # Check for duplicate name (excluding current project)
        existing = (
            tenant_filter(db.query(TestProject), TestProject)
            .filter(TestProject.name == data['name'], TestProject.id != project_id)
            .first()
        )
        if existing:
            return None, 'Project name already exists'
        project.name = data['name']

    if 'description' in data:
        project.description = data['description']
    if 'status' in data:
        if data['status'] not in VALID_STATUSES:
            return None, f'Invalid status: {data["status"]}'
        project.status = data['status']
    if 'responsible_user_id' in data:
        project.responsible_user_id = data['responsible_user_id']
    if 'start_time' in data:
        project.start_time = _parse_datetime(data['start_time'])
    if 'end_time' in data:
        project.end_time = _parse_datetime(data['end_time'])

    db.commit()
    db.refresh(project)
    return _project_to_dict(project, db), None


def delete_project(db, project_id):
    """Delete a test project within the current tenant.

    Returns ``True`` on success or ``False`` if not found.
    Cascades deletion to test results. Unlinks assigned test cases.
    """
    project = (
        tenant_filter(db.query(TestProject), TestProject)
        .filter_by(id=project_id)
        .first()
    )
    if not project:
        return False

    # Unlink test cases (set their test_project_id to NULL)
    (
        tenant_filter(db.query(TestCase), TestCase)
        .filter(TestCase.test_project_id == project_id)
        .update({TestCase.test_project_id: None}, synchronize_session='fetch')
    )

    # Delete test results (cascaded by relationship, but explicit for clarity)
    db.query(TestResult).filter(TestResult.project_id == project_id).delete()

    db.delete(project)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Test case assignment
# ---------------------------------------------------------------------------

def assign_test_cases(db, project_id, test_case_ids):
    """Assign test cases to a project by updating their test_project_id.

    Returns ``(result_dict, None)`` on success or ``(None, error)`` on failure.
    """
    project = (
        tenant_filter(db.query(TestProject), TestProject)
        .filter_by(id=project_id)
        .first()
    )
    if not project:
        return None, 'Project not found'

    # Verify all cases belong to this tenant
    cases = (
        tenant_filter(db.query(TestCase), TestCase)
        .filter(TestCase.id.in_(test_case_ids))
        .all()
    )

    for case in cases:
        case.test_project_id = project_id

    db.commit()
    return {'assigned': len(cases)}, None


def assign_user_to_case(db, project_id, test_case_id, user_id):
    """Assign (or unassign) a user to a test case within a project.

    Pass ``user_id=None`` to clear the assignment.
    Returns ``(case_dict, None)`` or ``(None, error)``.
    """
    project = (
        tenant_filter(db.query(TestProject), TestProject)
        .filter_by(id=project_id)
        .first()
    )
    if not project:
        return None, 'Project not found'

    case = (
        tenant_filter(db.query(TestCase), TestCase)
        .filter(TestCase.id == test_case_id, TestCase.test_project_id == project_id)
        .first()
    )
    if not case:
        return None, 'Test case not found in this project'

    if user_id:
        from flask import g
        user = (
            db.query(User)
            .filter(User.id == user_id, User.tenant_id == g.tenant_id)
            .first()
        )
        if not user:
            return None, 'User not found in this organization'
        case.responsible_user_id = user.id
    else:
        case.responsible_user_id = None

    db.commit()
    return {
        'test_case_id': case.id,
        'assigned_user_id': str(case.responsible_user_id) if case.responsible_user_id else None,
    }, None


# ---------------------------------------------------------------------------
# Test result management
# ---------------------------------------------------------------------------

def update_test_result(db, project_id, data):
    """Update or create a test result for a case in a project (UPSERT).

    Returns ``(result_dict, None)`` on success or ``(None, error)`` on failure.
    """
    project = (
        tenant_filter(db.query(TestProject), TestProject)
        .filter_by(id=project_id)
        .first()
    )
    if not project:
        return None, 'Project not found'

    test_case_id = data.get('test_case_id')
    if not test_case_id:
        return None, 'test_case_id is required'

    # Validate status if provided
    status = data.get('status', 'not_tested')
    if status not in VALID_RESULT_STATUSES:
        return None, f'Invalid result status: {status}'

    result = (
        db.query(TestResult)
        .filter_by(project_id=project_id, test_case_id=test_case_id)
        .first()
    )

    if result:
        # Update existing
        result.status = data.get('status', result.status)
        result.notes = data.get('notes', result.notes)
        result.known_issues = data.get('known_issues', result.known_issues)
        result.blocked_reason = data.get('blocked_reason', result.blocked_reason)
        result.tested_at = datetime.now(timezone.utc)
    else:
        # Create new
        result = TestResult(
            project_id=project_id,
            test_case_id=test_case_id,
            status=status,
            notes=data.get('notes'),
            known_issues=data.get('known_issues'),
            blocked_reason=data.get('blocked_reason'),
        )
        set_tenant_fields(result)
        db.add(result)

    db.commit()
    db.refresh(result)
    return _result_to_dict(result), None


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def get_project_stats(db, project_id):
    """Return statistics for a project.

    Returns ``(stats_dict, None)`` on success or ``(None, error)`` on failure.
    """
    project = (
        tenant_filter(db.query(TestProject), TestProject)
        .filter_by(id=project_id)
        .first()
    )
    if not project:
        return None, 'Project not found'

    return _compute_stats(db, project_id), None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_datetime(value):
    """Parse a datetime string or return None."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        # Support ISO format
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None


def _assign_cases_to_project(db, project_id, test_case_ids):
    """Internal helper to assign cases to a project during creation."""
    cases = (
        tenant_filter(db.query(TestCase), TestCase)
        .filter(TestCase.id.in_(test_case_ids))
        .all()
    )
    for case in cases:
        case.test_project_id = project_id
