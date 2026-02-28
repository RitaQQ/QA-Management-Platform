"""
Test case service -- CRUD, CSV import/export, and TC ID generation.

All database queries are scoped to the current tenant via ``tenant_filter``
and ``set_tenant_fields`` from :mod:`middleware.tenant`.
"""
import csv
import io
import logging

from database.models import TestCase, ProductTag, TestCaseTag
from middleware.tenant import tenant_filter, set_tenant_fields

logger = logging.getLogger(__name__)

# Valid values for validation
VALID_PRIORITIES = ('low', 'medium', 'high')
VALID_STATUSES = ('draft', 'ready', 'in_progress', 'completed', 'blocked')


# ---------------------------------------------------------------------------
# TC ID generation
# ---------------------------------------------------------------------------

def get_next_tc_id(db):
    """Generate the next TC ID (TC00001 format) for the current tenant."""
    last = (
        tenant_filter(db.query(TestCase), TestCase)
        .order_by(TestCase.id.desc())
        .first()
    )
    if last and last.tc_id:
        num = int(last.tc_id.replace('TC', ''))
        return f"TC{num + 1:05d}"
    return "TC00001"


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def _case_to_dict(case, db=None):
    """Serialize a :class:`TestCase` ORM instance to a plain dict.

    When *db* is provided, eagerly loads associated product tags.
    """
    tags = []
    if db:
        tag_ids = (
            db.query(TestCaseTag.product_tag_id)
            .filter(TestCaseTag.test_case_id == case.id)
            .all()
        )
        if tag_ids:
            tags = (
                db.query(ProductTag)
                .filter(ProductTag.id.in_([t[0] for t in tag_ids]))
                .all()
            )

    return {
        'id': case.id,
        'tc_id': case.tc_id,
        'title': case.title,
        'user_role': case.user_role,
        'feature_description': case.feature_description,
        'acceptance_criteria': case.acceptance_criteria,
        'test_notes': case.test_notes,
        'priority': case.priority,
        'status': case.status,
        'test_project_id': case.test_project_id,
        'responsible_user_id': str(case.responsible_user_id) if case.responsible_user_id else None,
        'estimated_hours': case.estimated_hours,
        'actual_hours': case.actual_hours,
        'product_tags': [
            {'id': t.id, 'name': t.name, 'color': t.color}
            for t in tags
        ],
        'created_at': case.created_at.isoformat() if case.created_at else None,
        'updated_at': case.updated_at.isoformat() if case.updated_at else None,
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def list_test_cases(db, filters=None):
    """Return all test cases for the current tenant, with optional filters.

    Supported filter keys: ``priority``, ``status``, ``tag_id``, ``project_id``.
    """
    query = tenant_filter(db.query(TestCase), TestCase)
    filters = filters or {}

    if filters.get('priority'):
        query = query.filter(TestCase.priority == filters['priority'])
    if filters.get('status'):
        query = query.filter(TestCase.status == filters['status'])
    if filters.get('project_id'):
        query = query.filter(TestCase.test_project_id == filters['project_id'])
    if filters.get('tag_id'):
        tag_id = filters['tag_id']
        case_ids = (
            db.query(TestCaseTag.test_case_id)
            .filter(TestCaseTag.product_tag_id == tag_id)
            .subquery()
        )
        query = query.filter(TestCase.id.in_(case_ids))

    cases = query.order_by(TestCase.id.asc()).all()
    return [_case_to_dict(c, db) for c in cases]


def get_test_case(db, case_id):
    """Return a single test case dict, or ``None`` if not found."""
    case = (
        tenant_filter(db.query(TestCase), TestCase)
        .filter_by(id=case_id)
        .first()
    )
    if not case:
        return None
    return _case_to_dict(case, db)


def create_test_case(db, data):
    """Create a new test case and return ``(case_dict, None)`` or ``(None, error)``.

    Required field: ``title``.
    """
    if not data.get('title'):
        return None, 'title is required'

    priority = data.get('priority', 'medium')
    if priority not in VALID_PRIORITIES:
        return None, f'Invalid priority: {priority}'

    status = data.get('status', 'draft')
    if status not in VALID_STATUSES:
        return None, f'Invalid status: {status}'

    tc_id = get_next_tc_id(db)

    case = TestCase(
        tc_id=tc_id,
        title=data['title'],
        user_role=data.get('user_role'),
        feature_description=data.get('feature_description'),
        acceptance_criteria=data.get('acceptance_criteria'),
        test_notes=data.get('test_notes'),
        priority=priority,
        status=status,
        test_project_id=data.get('test_project_id'),
        responsible_user_id=data.get('responsible_user_id'),
        estimated_hours=data.get('estimated_hours', 0),
        actual_hours=data.get('actual_hours', 0),
    )
    set_tenant_fields(case)
    db.add(case)
    db.flush()

    # Handle product tags
    tag_ids = data.get('tag_ids', [])
    _sync_tags(db, case.id, tag_ids)

    db.commit()
    db.refresh(case)
    return _case_to_dict(case, db), None


def update_test_case(db, case_id, data):
    """Update an existing test case.

    Returns ``(case_dict, None)`` on success, ``(None, 'Not found')`` if missing,
    or ``(None, error_message)`` on validation failure.
    """
    case = (
        tenant_filter(db.query(TestCase), TestCase)
        .filter_by(id=case_id)
        .first()
    )
    if not case:
        return None, 'Not found'

    if 'title' in data:
        case.title = data['title']
    if 'user_role' in data:
        case.user_role = data['user_role']
    if 'feature_description' in data:
        case.feature_description = data['feature_description']
    if 'acceptance_criteria' in data:
        case.acceptance_criteria = data['acceptance_criteria']
    if 'test_notes' in data:
        case.test_notes = data['test_notes']
    if 'priority' in data:
        if data['priority'] not in VALID_PRIORITIES:
            return None, f'Invalid priority: {data["priority"]}'
        case.priority = data['priority']
    if 'status' in data:
        if data['status'] not in VALID_STATUSES:
            return None, f'Invalid status: {data["status"]}'
        case.status = data['status']
    if 'test_project_id' in data:
        case.test_project_id = data['test_project_id']
    if 'responsible_user_id' in data:
        case.responsible_user_id = data['responsible_user_id']
    if 'estimated_hours' in data:
        case.estimated_hours = data['estimated_hours']
    if 'actual_hours' in data:
        case.actual_hours = data['actual_hours']

    # Handle tag updates
    if 'tag_ids' in data:
        _sync_tags(db, case.id, data['tag_ids'])

    db.commit()
    db.refresh(case)
    return _case_to_dict(case, db), None


def delete_test_case(db, case_id):
    """Delete a test case within the current tenant.

    Returns ``True`` on success or ``False`` if not found.
    """
    case = (
        tenant_filter(db.query(TestCase), TestCase)
        .filter_by(id=case_id)
        .first()
    )
    if not case:
        return False

    # Remove tag associations first
    db.query(TestCaseTag).filter(TestCaseTag.test_case_id == case.id).delete()
    db.delete(case)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# CSV export / import
# ---------------------------------------------------------------------------

def export_csv(db):
    """Export all test cases for the current tenant as a CSV string.

    Columns: TC ID, title, user_role, feature_description,
    acceptance_criteria, priority, status, product_tags.
    """
    cases = (
        tenant_filter(db.query(TestCase), TestCase)
        .order_by(TestCase.id.asc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        'TC ID', 'Title', 'User Role', 'Feature Description',
        'Acceptance Criteria', 'Priority', 'Status', 'Tags',
    ])

    for case in cases:
        # Fetch tags for this case
        tag_names = _get_tag_names_for_case(db, case.id)

        writer.writerow([
            case.tc_id,
            case.title or '',
            case.user_role or '',
            case.feature_description or '',
            case.acceptance_criteria or '',
            case.priority or 'medium',
            case.status or 'draft',
            ','.join(tag_names),
        ])

    return output.getvalue()


def import_csv(db, csv_content):
    """Import test cases from CSV content string.

    Returns a dict with ``created`` (count), ``errors`` (list of error messages),
    and ``total`` (total rows processed).
    """
    from services.product_tag_service import get_or_create_tag

    reader = csv.reader(io.StringIO(csv_content))

    # Skip header row
    try:
        header = next(reader)
    except StopIteration:
        return {'created': 0, 'errors': ['Empty CSV file'], 'total': 0}

    created = 0
    errors = []
    total = 0

    for row_num, row in enumerate(reader, start=2):
        total += 1

        if len(row) < 2:
            errors.append(f'Row {row_num}: insufficient columns')
            continue

        # Parse columns: TC ID (ignored, auto-generated), title, user_role,
        # feature_description, acceptance_criteria, priority, status, tags
        title = row[1].strip() if len(row) > 1 else ''
        if not title:
            errors.append(f'Row {row_num}: title is required')
            continue

        user_role = row[2].strip() if len(row) > 2 else ''
        feature_description = row[3].strip() if len(row) > 3 else ''
        acceptance_criteria = row[4].strip() if len(row) > 4 else ''
        priority = row[5].strip() if len(row) > 5 else 'medium'
        status = row[6].strip() if len(row) > 6 else 'draft'
        tag_string = row[7].strip() if len(row) > 7 else ''

        # Validate priority and status
        if priority not in VALID_PRIORITIES:
            priority = 'medium'
        if status not in VALID_STATUSES:
            status = 'draft'

        try:
            tc_id = get_next_tc_id(db)
            case = TestCase(
                tc_id=tc_id,
                title=title,
                user_role=user_role or None,
                feature_description=feature_description or None,
                acceptance_criteria=acceptance_criteria or None,
                priority=priority,
                status=status,
            )
            set_tenant_fields(case)
            db.add(case)
            db.flush()

            # Handle tags
            if tag_string:
                tag_names = [t.strip() for t in tag_string.split(',') if t.strip()]
                for tag_name in tag_names:
                    tag = get_or_create_tag(db, tag_name)
                    # Check if association already exists
                    existing = (
                        db.query(TestCaseTag)
                        .filter_by(test_case_id=case.id, product_tag_id=tag.id)
                        .first()
                    )
                    if not existing:
                        db.add(TestCaseTag(
                            test_case_id=case.id,
                            product_tag_id=tag.id,
                        ))

            created += 1
        except Exception as exc:
            logger.warning('CSV import row %d failed: %s', row_num, exc)
            errors.append(f'Row {row_num}: {str(exc)}')

    db.commit()
    return {'created': created, 'errors': errors, 'total': total}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sync_tags(db, case_id, tag_ids):
    """Replace all tag associations for *case_id* with the given *tag_ids*."""
    # Remove existing associations
    db.query(TestCaseTag).filter(TestCaseTag.test_case_id == case_id).delete()
    # Add new associations
    for tid in tag_ids:
        db.add(TestCaseTag(test_case_id=case_id, product_tag_id=tid))
    db.flush()


def _get_tag_names_for_case(db, case_id):
    """Return a list of tag names for a given test case."""
    tag_ids = (
        db.query(TestCaseTag.product_tag_id)
        .filter(TestCaseTag.test_case_id == case_id)
        .all()
    )
    if not tag_ids:
        return []
    tags = (
        db.query(ProductTag)
        .filter(ProductTag.id.in_([t[0] for t in tag_ids]))
        .all()
    )
    return [t.name for t in tags]
