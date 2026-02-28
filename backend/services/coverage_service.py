"""
API-TestCase coverage service -- linking, dashboard, and alerts.

Provides functions for creating/removing links between API endpoints and
test cases, computing coverage statistics, and generating coverage alerts
for unhealthy or uncovered APIs.

All database queries are scoped to the current tenant via ``tenant_filter``
and ``set_tenant_fields`` from :mod:`middleware.tenant`.
"""
import logging

from database.models import ApiEndpoint, TestCase, ApiTestcaseLink
from middleware.tenant import tenant_filter, set_tenant_fields, get_tenant_id

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Link / Unlink
# ---------------------------------------------------------------------------

def link_api_to_test_case(db, api_id, test_case_id, link_type='covers'):
    """Create a link between an API endpoint and a test case.

    Both objects must belong to the current tenant.

    Returns
    -------
    tuple
        ``(link_dict, None)`` on success or ``(None, error_message)``
        on failure.
    """
    endpoint = (
        tenant_filter(db.query(ApiEndpoint), ApiEndpoint)
        .filter_by(id=api_id)
        .first()
    )
    if not endpoint:
        return None, 'API endpoint not found'

    case = (
        tenant_filter(db.query(TestCase), TestCase)
        .filter_by(id=test_case_id)
        .first()
    )
    if not case:
        return None, 'Test case not found'

    # Check for existing link
    existing = (
        db.query(ApiTestcaseLink)
        .filter_by(api_id=api_id, test_case_id=test_case_id)
        .first()
    )
    if existing:
        return None, 'Link already exists'

    link = ApiTestcaseLink(
        api_id=api_id,
        test_case_id=test_case_id,
        link_type=link_type,
    )
    set_tenant_fields(link)
    db.add(link)
    db.commit()

    return {
        'api_id': api_id,
        'test_case_id': test_case_id,
        'link_type': link_type,
    }, None


def unlink_api_from_test_case(db, api_id, test_case_id):
    """Remove a link between an API endpoint and a test case.

    The API endpoint must belong to the current tenant.

    Returns
    -------
    tuple
        ``({'removed': True}, None)`` on success or
        ``(None, error_message)`` on failure.
    """
    # Verify the API belongs to this tenant
    endpoint = (
        tenant_filter(db.query(ApiEndpoint), ApiEndpoint)
        .filter_by(id=api_id)
        .first()
    )
    if not endpoint:
        return None, 'API endpoint not found'

    link = (
        db.query(ApiTestcaseLink)
        .filter_by(api_id=api_id, test_case_id=test_case_id)
        .first()
    )
    if not link:
        return None, 'Link not found'

    db.delete(link)
    db.commit()
    return {'removed': True}, None


# ---------------------------------------------------------------------------
# Coverage Dashboard
# ---------------------------------------------------------------------------

def get_coverage_dashboard(db):
    """Return coverage overview for the current tenant.

    Returns a dict with:
    - ``total_apis``: total API endpoints
    - ``covered_apis``: APIs with at least one linked test case
    - ``uncovered_apis``: count of APIs with no linked test cases
    - ``coverage_percent``: percentage covered (0-100)
    - ``uncovered_api_list``: details of uncovered APIs
    """
    tenant_id = get_tenant_id()

    total_apis = (
        tenant_filter(db.query(ApiEndpoint), ApiEndpoint).count()
    )

    # API IDs that have at least one linked test case
    covered_api_ids = (
        db.query(ApiTestcaseLink.api_id)
        .join(ApiEndpoint, ApiTestcaseLink.api_id == ApiEndpoint.id)
        .filter(ApiEndpoint.tenant_id == tenant_id)
        .distinct()
        .all()
    )
    covered_id_set = {row[0] for row in covered_api_ids}
    covered_count = len(covered_id_set)

    # Find uncovered APIs
    if covered_id_set:
        uncovered_apis = (
            tenant_filter(db.query(ApiEndpoint), ApiEndpoint)
            .filter(~ApiEndpoint.id.in_(covered_id_set))
            .all()
        )
    else:
        uncovered_apis = (
            tenant_filter(db.query(ApiEndpoint), ApiEndpoint).all()
        )

    coverage_percent = (covered_count / total_apis * 100) if total_apis > 0 else 0

    return {
        'total_apis': total_apis,
        'covered_apis': covered_count,
        'uncovered_apis': total_apis - covered_count,
        'coverage_percent': round(coverage_percent, 1),
        'uncovered_api_list': [
            {
                'id': a.id,
                'name': a.name,
                'url': a.url,
                'status': a.status,
            }
            for a in uncovered_apis
        ],
    }


# ---------------------------------------------------------------------------
# Cross-reference queries
# ---------------------------------------------------------------------------

def get_api_with_linked_cases(db, api_id):
    """Return API endpoint details with its linked test cases.

    Returns
    -------
    tuple
        ``(result_dict, None)`` on success or ``(None, error_message)``
        if the endpoint is not found within the current tenant.
    """
    endpoint = (
        tenant_filter(db.query(ApiEndpoint), ApiEndpoint)
        .filter_by(id=api_id)
        .first()
    )
    if not endpoint:
        return None, 'API endpoint not found'

    links = db.query(ApiTestcaseLink).filter_by(api_id=api_id).all()
    case_ids = [link.test_case_id for link in links]
    cases = (
        db.query(TestCase).filter(TestCase.id.in_(case_ids)).all()
        if case_ids else []
    )

    return {
        'api': {
            'id': endpoint.id,
            'name': endpoint.name,
            'url': endpoint.url,
            'status': endpoint.status,
        },
        'linked_test_cases': [
            {
                'id': c.id,
                'tc_id': c.tc_id,
                'title': c.title,
                'status': c.status,
            }
            for c in cases
        ],
    }, None


def get_case_with_linked_apis(db, case_id):
    """Return test case details with its linked API endpoints.

    Returns
    -------
    tuple
        ``(result_dict, None)`` on success or ``(None, error_message)``
        if the test case is not found within the current tenant.
    """
    case = (
        tenant_filter(db.query(TestCase), TestCase)
        .filter_by(id=case_id)
        .first()
    )
    if not case:
        return None, 'Test case not found'

    links = db.query(ApiTestcaseLink).filter_by(test_case_id=case_id).all()
    api_ids = [link.api_id for link in links]
    apis = (
        db.query(ApiEndpoint).filter(ApiEndpoint.id.in_(api_ids)).all()
        if api_ids else []
    )

    return {
        'test_case': {
            'id': case.id,
            'tc_id': case.tc_id,
            'title': case.title,
        },
        'linked_apis': [
            {
                'id': a.id,
                'name': a.name,
                'url': a.url,
                'status': a.status,
            }
            for a in apis
        ],
    }, None


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

def get_alerts(db):
    """Return coverage alerts for the current tenant.

    Two alert types:
    1. ``unhealthy_api_with_cases``: unhealthy APIs that have linked test cases
       (impact analysis -- these test cases may be affected).
    2. ``uncovered_unhealthy_api``: unhealthy APIs with no linked test cases
       (coverage gap -- no tests monitor this failing API).

    Returns a dict with ``data`` (list of alerts) and ``total_alerts``.
    """
    tenant_id = get_tenant_id()
    alerts = []

    # --- Alert type 1: unhealthy APIs with linked test cases ----------------
    unhealthy_with_cases = (
        db.query(ApiEndpoint)
        .join(ApiTestcaseLink, ApiEndpoint.id == ApiTestcaseLink.api_id)
        .filter(
            ApiEndpoint.tenant_id == tenant_id,
            ApiEndpoint.status == 'unhealthy',
        )
        .distinct()
        .all()
    )

    for api in unhealthy_with_cases:
        links = db.query(ApiTestcaseLink).filter_by(api_id=api.id).all()
        case_ids = [link.test_case_id for link in links]
        cases = db.query(TestCase).filter(TestCase.id.in_(case_ids)).all()

        alerts.append({
            'type': 'unhealthy_api_with_cases',
            'api': {
                'id': api.id,
                'name': api.name,
                'url': api.url,
                'last_error': api.last_error,
            },
            'affected_test_cases': [
                {'id': c.id, 'tc_id': c.tc_id, 'title': c.title}
                for c in cases
            ],
        })

    # --- Alert type 2: uncovered unhealthy APIs -----------------------------
    covered_ids_rows = db.query(ApiTestcaseLink.api_id).distinct().all()
    covered_ids = [row[0] for row in covered_ids_rows]

    uncovered_unhealthy_query = (
        tenant_filter(db.query(ApiEndpoint), ApiEndpoint)
        .filter(ApiEndpoint.status == 'unhealthy')
    )
    if covered_ids:
        uncovered_unhealthy_query = uncovered_unhealthy_query.filter(
            ~ApiEndpoint.id.in_(covered_ids)
        )

    for api in uncovered_unhealthy_query.all():
        alerts.append({
            'type': 'uncovered_unhealthy_api',
            'api': {
                'id': api.id,
                'name': api.name,
                'url': api.url,
                'last_error': api.last_error,
            },
            'affected_test_cases': [],
        })

    return {'data': alerts, 'total_alerts': len(alerts)}
