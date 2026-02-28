"""
Product tag service -- CRUD operations for product tags.

All database queries are scoped to the current tenant via ``tenant_filter``
and ``set_tenant_fields`` from :mod:`middleware.tenant`.
"""
import logging

from database.models import ProductTag, TestCaseTag
from middleware.tenant import tenant_filter, set_tenant_fields

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def _tag_to_dict(tag):
    """Serialize a :class:`ProductTag` ORM instance to a plain dict."""
    return {
        'id': tag.id,
        'name': tag.name,
        'description': tag.description,
        'color': tag.color,
        'created_at': tag.created_at.isoformat() if tag.created_at else None,
        'updated_at': tag.updated_at.isoformat() if tag.updated_at else None,
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def list_tags(db):
    """Return all product tags for the current tenant."""
    tags = (
        tenant_filter(db.query(ProductTag), ProductTag)
        .order_by(ProductTag.name.asc())
        .all()
    )
    return [_tag_to_dict(t) for t in tags]


def get_tag(db, tag_id):
    """Return a single product tag dict, or ``None`` if not found."""
    tag = (
        tenant_filter(db.query(ProductTag), ProductTag)
        .filter_by(id=tag_id)
        .first()
    )
    if not tag:
        return None
    return _tag_to_dict(tag)


def create_tag(db, data):
    """Create a new product tag.

    Returns ``(tag_dict, None)`` on success or ``(None, error_message)`` on failure.
    """
    if not data.get('name'):
        return None, 'name is required'

    # Check for duplicate name within the tenant
    existing = (
        tenant_filter(db.query(ProductTag), ProductTag)
        .filter_by(name=data['name'])
        .first()
    )
    if existing:
        return None, f'Tag with name "{data["name"]}" already exists'

    tag = ProductTag(
        name=data['name'],
        description=data.get('description'),
        color=data.get('color', '#007bff'),
    )
    set_tenant_fields(tag)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return _tag_to_dict(tag), None


def update_tag(db, tag_id, data):
    """Update an existing product tag.

    Returns ``(tag_dict, None)`` on success, ``(None, 'Not found')`` if missing,
    or ``(None, error_message)`` on validation failure.
    """
    tag = (
        tenant_filter(db.query(ProductTag), ProductTag)
        .filter_by(id=tag_id)
        .first()
    )
    if not tag:
        return None, 'Not found'

    if 'name' in data:
        # Check for duplicate name within tenant (excluding current tag)
        existing = (
            tenant_filter(db.query(ProductTag), ProductTag)
            .filter(ProductTag.name == data['name'], ProductTag.id != tag_id)
            .first()
        )
        if existing:
            return None, f'Tag with name "{data["name"]}" already exists'
        tag.name = data['name']

    if 'description' in data:
        tag.description = data['description']
    if 'color' in data:
        tag.color = data['color']

    db.commit()
    db.refresh(tag)
    return _tag_to_dict(tag), None


def delete_tag(db, tag_id):
    """Delete a product tag within the current tenant.

    Returns ``True`` on success or ``False`` if not found.
    Also removes all test case associations for this tag.
    """
    tag = (
        tenant_filter(db.query(ProductTag), ProductTag)
        .filter_by(id=tag_id)
        .first()
    )
    if not tag:
        return False

    # Remove associations
    db.query(TestCaseTag).filter(TestCaseTag.product_tag_id == tag.id).delete()
    db.delete(tag)
    db.commit()
    return True


def get_or_create_tag(db, name):
    """Find a product tag by *name* within the current tenant, or create it.

    Used during CSV import to resolve tag references.
    Returns the :class:`ProductTag` ORM instance.
    """
    tag = (
        tenant_filter(db.query(ProductTag), ProductTag)
        .filter_by(name=name)
        .first()
    )
    if tag:
        return tag

    tag = ProductTag(
        name=name,
        color='#007bff',
    )
    set_tenant_fields(tag)
    db.add(tag)
    db.flush()
    return tag
