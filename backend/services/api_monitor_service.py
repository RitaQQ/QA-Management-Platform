"""
API monitoring service — endpoint CRUD, health checks, history, and uptime.

All database queries are scoped to the current tenant via ``tenant_filter``
and ``set_tenant_fields`` from :mod:`middleware.tenant`.
"""
import json
import time
import logging
from datetime import datetime, timedelta, timezone

import requests as http_requests

from database.models import ApiEndpoint, ApiCheckHistory, utcnow
from middleware.tenant import tenant_filter, set_tenant_fields
from services.notification_service import (
    notify_api_unhealthy, notify_api_recovered, NOTIFICATION_THRESHOLD,
)

logger = logging.getLogger(__name__)

# Health-check constants
REQUEST_TIMEOUT = 10  # seconds
VALID_METHODS = ('GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS')


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------

def list_endpoints(db):
    """Return all API endpoints for the current tenant."""
    endpoints = tenant_filter(db.query(ApiEndpoint), ApiEndpoint).all()
    return [_endpoint_to_dict(ep) for ep in endpoints]


def get_endpoint(db, endpoint_id):
    """Return a single endpoint by *endpoint_id* within the current tenant.

    Returns ``None`` if not found.
    """
    return (
        tenant_filter(db.query(ApiEndpoint), ApiEndpoint)
        .filter_by(id=endpoint_id)
        .first()
    )


def create_endpoint(db, data):
    """Create a new API endpoint and return its dict representation.

    Parameters
    ----------
    data : dict
        Must include ``name`` and ``url``.  Optional keys: ``method``,
        ``request_body``, ``headers``, ``expected_status_code``,
        ``check_interval_seconds``, ``is_active``.

    Returns
    -------
    tuple
        ``(endpoint_dict, None)`` on success or ``(None, error_message)``
        on validation failure.
    """
    # Validate required fields
    if not data.get('name'):
        return None, 'name is required'
    if not data.get('url'):
        return None, 'url is required'

    url = data['url']
    if not url.startswith(('http://', 'https://')):
        return None, 'url must start with http:// or https://'

    method = (data.get('method') or 'GET').upper()
    if method not in VALID_METHODS:
        return None, f'Invalid method: {method}'

    # Parse headers if provided as string
    headers_value = data.get('headers')
    if isinstance(headers_value, dict):
        headers_value = json.dumps(headers_value)

    endpoint = ApiEndpoint(
        name=data['name'],
        url=url,
        method=method,
        request_body=data.get('request_body'),
        headers=headers_value,
        expected_status_code=data.get('expected_status_code', 200),
        check_interval_seconds=data.get('check_interval_seconds', 60),
        is_active=data.get('is_active', True),
    )
    set_tenant_fields(endpoint)
    db.add(endpoint)
    db.commit()
    db.refresh(endpoint)

    return _endpoint_to_dict(endpoint), None


def update_endpoint(db, endpoint_id, data):
    """Update an existing endpoint within the current tenant.

    Returns
    -------
    tuple
        ``(endpoint_dict, None)`` on success, ``(None, 'Not found')`` if
        the endpoint does not exist within this tenant, or
        ``(None, error_message)`` on validation failure.
    """
    endpoint = get_endpoint(db, endpoint_id)
    if not endpoint:
        return None, 'Not found'

    # Updatable fields
    if 'name' in data:
        endpoint.name = data['name']
    if 'url' in data:
        url = data['url']
        if not url.startswith(('http://', 'https://')):
            return None, 'url must start with http:// or https://'
        endpoint.url = url
    if 'method' in data:
        method = data['method'].upper()
        if method not in VALID_METHODS:
            return None, f'Invalid method: {method}'
        endpoint.method = method
    if 'request_body' in data:
        endpoint.request_body = data['request_body']
    if 'headers' in data:
        headers_value = data['headers']
        if isinstance(headers_value, dict):
            headers_value = json.dumps(headers_value)
        endpoint.headers = headers_value
    if 'expected_status_code' in data:
        endpoint.expected_status_code = data['expected_status_code']
    if 'check_interval_seconds' in data:
        endpoint.check_interval_seconds = data['check_interval_seconds']
    if 'is_active' in data:
        endpoint.is_active = data['is_active']

    db.commit()
    db.refresh(endpoint)
    return _endpoint_to_dict(endpoint), None


def delete_endpoint(db, endpoint_id):
    """Delete an endpoint within the current tenant.

    Returns ``True`` on success or ``False`` if not found.
    """
    endpoint = get_endpoint(db, endpoint_id)
    if not endpoint:
        return False
    db.delete(endpoint)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def check_endpoint(db, endpoint_id):
    """Execute a health check for a single endpoint and persist the result.

    Returns
    -------
    tuple
        ``(result_dict, None)`` on success or ``(None, error_message)`` if
        the endpoint is not found.
    """
    endpoint = get_endpoint(db, endpoint_id)
    if not endpoint:
        return None, 'Not found'

    prev_status = endpoint.status
    result = _perform_check(endpoint)

    # Persist history entry
    history = ApiCheckHistory(
        api_id=endpoint.id,
        status=result['status'],
        status_code=result.get('status_code'),
        response_time_ms=result.get('response_time_ms'),
        error_message=result.get('error_message'),
    )
    set_tenant_fields(history)
    db.add(history)

    # Update endpoint summary fields
    endpoint.status = result['status']
    endpoint.response_time = result.get('response_time_ms', 0) / 1000.0
    endpoint.last_check = utcnow()
    endpoint.last_error = result.get('error_message')

    if result['status'] == 'healthy':
        endpoint.error_count = 0
    else:
        endpoint.error_count = (endpoint.error_count or 0) + 1

    db.commit()
    db.refresh(endpoint)

    # --- Notifications -------------------------------------------------------
    # Fire exactly once when error_count first reaches the threshold
    if (endpoint.status == 'unhealthy'
            and endpoint.error_count == NOTIFICATION_THRESHOLD):
        try:
            notify_api_unhealthy(db, endpoint)
        except Exception:
            logger.exception('Failed to send unhealthy notification')

    # Fire when an endpoint transitions from unhealthy back to healthy
    if endpoint.status == 'healthy' and prev_status == 'unhealthy':
        try:
            notify_api_recovered(db, endpoint)
        except Exception:
            logger.exception('Failed to send recovery notification')

    return {
        'endpoint': _endpoint_to_dict(endpoint),
        'check': result,
    }, None


def check_all_endpoints(db):
    """Check all active endpoints for the current tenant.

    Returns a list of ``(endpoint_id, result_dict)`` tuples.
    """
    endpoints = (
        tenant_filter(db.query(ApiEndpoint), ApiEndpoint)
        .filter_by(is_active=True)
        .all()
    )

    results = []
    notification_queue = []  # (type, endpoint) tuples for post-commit dispatch

    for endpoint in endpoints:
        prev_status = endpoint.status
        result = _perform_check(endpoint)

        history = ApiCheckHistory(
            api_id=endpoint.id,
            status=result['status'],
            status_code=result.get('status_code'),
            response_time_ms=result.get('response_time_ms'),
            error_message=result.get('error_message'),
        )
        set_tenant_fields(history)
        db.add(history)

        endpoint.status = result['status']
        endpoint.response_time = result.get('response_time_ms', 0) / 1000.0
        endpoint.last_check = utcnow()
        endpoint.last_error = result.get('error_message')

        if result['status'] == 'healthy':
            endpoint.error_count = 0
        else:
            endpoint.error_count = (endpoint.error_count or 0) + 1

        # Queue notifications (sent after commit)
        if (endpoint.status == 'unhealthy'
                and endpoint.error_count == NOTIFICATION_THRESHOLD):
            notification_queue.append(('unhealthy', endpoint))
        elif endpoint.status == 'healthy' and prev_status == 'unhealthy':
            notification_queue.append(('recovered', endpoint))

        results.append((endpoint.id, result))

    db.commit()

    # Dispatch queued notifications after successful commit
    for ntype, ep in notification_queue:
        try:
            if ntype == 'unhealthy':
                notify_api_unhealthy(db, ep)
            else:
                notify_api_recovered(db, ep)
        except Exception:
            logger.exception('Failed to send %s notification for %s', ntype, ep.name)

    return results


# ---------------------------------------------------------------------------
# History and uptime
# ---------------------------------------------------------------------------

def get_history(db, endpoint_id, days=1):
    """Return check history for *endpoint_id* within the last *days* days.

    Returns ``(list_of_dicts, None)`` on success or ``(None, error_message)``
    if the endpoint is not found.
    """
    endpoint = get_endpoint(db, endpoint_id)
    if not endpoint:
        return None, 'Not found'

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    records = (
        tenant_filter(db.query(ApiCheckHistory), ApiCheckHistory)
        .filter(
            ApiCheckHistory.api_id == endpoint_id,
            ApiCheckHistory.checked_at >= cutoff,
        )
        .order_by(ApiCheckHistory.checked_at.desc())
        .all()
    )

    return [_history_to_dict(r) for r in records], None


def get_uptime(db, endpoint_id, days=7):
    """Calculate uptime percentage for *endpoint_id* over *days* days.

    Returns ``(result_dict, None)`` on success or ``(None, error_message)``
    if the endpoint is not found.
    """
    endpoint = get_endpoint(db, endpoint_id)
    if not endpoint:
        return None, 'Not found'

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    base_query = (
        tenant_filter(db.query(ApiCheckHistory), ApiCheckHistory)
        .filter(
            ApiCheckHistory.api_id == endpoint_id,
            ApiCheckHistory.checked_at >= cutoff,
        )
    )

    total = base_query.count()
    healthy = base_query.filter(ApiCheckHistory.status == 'healthy').count()

    uptime_percent = (healthy / total * 100) if total > 0 else 0

    return {
        'uptime_percent': round(uptime_percent, 2),
        'total_checks': total,
        'healthy_checks': healthy,
        'period_days': days,
    }, None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _perform_check(endpoint):
    """Execute an HTTP request against *endpoint* and return a result dict.

    The result dict always contains ``status``, ``status_code``,
    ``response_time_ms``, and optionally ``error_message``.
    """
    try:
        # Build request parameters
        method = (endpoint.method or 'GET').upper()
        url = endpoint.url
        headers = {}
        if endpoint.headers:
            try:
                headers = json.loads(endpoint.headers)
            except (json.JSONDecodeError, TypeError):
                pass

        # Process request body with {{timestamp}} variable substitution
        body = endpoint.request_body
        if body and '{{timestamp}}' in body:
            body = body.replace('{{timestamp}}', str(int(time.time())))

        expected_status = endpoint.expected_status_code or 200

        start = time.time()
        response = http_requests.request(
            method=method,
            url=url,
            headers=headers,
            data=body,
            timeout=REQUEST_TIMEOUT,
        )
        elapsed_ms = int((time.time() - start) * 1000)

        if response.status_code == expected_status:
            status = 'healthy'
            error_message = None
        else:
            status = 'unhealthy'
            error_message = f'Expected {expected_status}, got {response.status_code}'

        return {
            'status': status,
            'status_code': response.status_code,
            'response_time_ms': elapsed_ms,
            'error_message': error_message,
        }

    except http_requests.exceptions.Timeout:
        return {
            'status': 'unhealthy',
            'status_code': None,
            'response_time_ms': REQUEST_TIMEOUT * 1000,
            'error_message': 'Request timeout',
        }
    except http_requests.exceptions.ConnectionError:
        return {
            'status': 'unhealthy',
            'status_code': None,
            'response_time_ms': 0,
            'error_message': 'Connection error',
        }
    except Exception as exc:
        logger.exception('Unexpected error during health check for %s', endpoint.url)
        return {
            'status': 'unhealthy',
            'status_code': None,
            'response_time_ms': 0,
            'error_message': str(exc),
        }


def _endpoint_to_dict(ep):
    """Serialize an :class:`ApiEndpoint` ORM instance to a plain dict."""
    return {
        'id': ep.id,
        'name': ep.name,
        'url': ep.url,
        'method': ep.method,
        'request_body': ep.request_body,
        'headers': ep.headers,
        'expected_status_code': ep.expected_status_code,
        'check_interval_seconds': ep.check_interval_seconds,
        'status': ep.status,
        'response_time': ep.response_time,
        'last_check': ep.last_check.isoformat() if ep.last_check else None,
        'error_count': ep.error_count,
        'last_error': ep.last_error,
        'is_active': ep.is_active,
        'created_at': ep.created_at.isoformat() if ep.created_at else None,
        'updated_at': ep.updated_at.isoformat() if ep.updated_at else None,
    }


def _history_to_dict(record):
    """Serialize an :class:`ApiCheckHistory` ORM instance to a plain dict."""
    return {
        'id': record.id,
        'status': record.status,
        'status_code': record.status_code,
        'response_time_ms': record.response_time_ms,
        'error_message': record.error_message,
        'checked_at': record.checked_at.isoformat() if record.checked_at else None,
    }
