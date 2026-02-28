"""
Tenant isolation middleware.

Provides helper functions for tenant-scoped database queries.
``g.tenant_id`` is already set by the ``jwt_required`` decorator
in :mod:`middleware.auth`.
"""
from flask import g


def get_tenant_id():
    """Return the current tenant ID from the Flask request context.

    Returns ``None`` when called outside a request or before
    ``jwt_required`` has run.
    """
    return getattr(g, 'tenant_id', None)


def tenant_filter(query, model):
    """Append a ``tenant_id`` filter to a SQLAlchemy *query*.

    Usage::

        query = tenant_filter(db.query(TestCase), TestCase)

    Raises
    ------
    ValueError
        If no tenant context is available (e.g. missing JWT).
    """
    tenant_id = get_tenant_id()
    if tenant_id is None:
        raise ValueError("No tenant context available")
    return query.filter(model.tenant_id == tenant_id)


def set_tenant_fields(instance):
    """Set ``tenant_id`` on a new ORM model *instance*.

    Usage::

        case = TestCase(title='...')
        set_tenant_fields(case)
        db.add(case)

    Returns the instance for convenient chaining.

    Raises
    ------
    ValueError
        If no tenant context is available.
    """
    tenant_id = get_tenant_id()
    if tenant_id is None:
        raise ValueError("No tenant context available")
    instance.tenant_id = tenant_id
    return instance
