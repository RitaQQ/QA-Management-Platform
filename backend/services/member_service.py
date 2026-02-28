"""
Member service -- invite links, member listing, role management.

All tenant-scoped operations use ``g.tenant_id`` / ``g.user_id`` from JWT.
"""
import secrets
from datetime import datetime, timedelta, timezone

from flask import g

from database.models import InviteLink, User, Organization
from services.user_service import hash_password


# ---------------------------------------------------------------------------
# Invite link management (admin only)
# ---------------------------------------------------------------------------

def create_invite_link(db, role='user', max_uses=None, expires_hours=None):
    """Create a new invite link for the current tenant.

    Returns the serialised invite link dict.
    """
    token = secrets.token_urlsafe(32)
    expires_at = None
    if expires_hours:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=int(expires_hours))

    link = InviteLink(
        tenant_id=g.tenant_id,
        token=token,
        role=role,
        created_by=g.user_id,
        max_uses=max_uses,
        expires_at=expires_at,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return _link_to_dict(link)


def list_invite_links(db):
    """Return all invite links for the current tenant."""
    links = (
        db.query(InviteLink)
        .filter(InviteLink.tenant_id == g.tenant_id)
        .order_by(InviteLink.created_at.desc())
        .all()
    )
    return [_link_to_dict(link) for link in links]


def revoke_invite_link(db, link_id):
    """Deactivate an invite link. Returns True on success, False if not found."""
    link = (
        db.query(InviteLink)
        .filter(
            InviteLink.id == link_id,
            InviteLink.tenant_id == g.tenant_id,
        )
        .first()
    )
    if not link:
        return False
    link.is_active = False
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Public invite validation / join
# ---------------------------------------------------------------------------

def validate_invite_token(db, token):
    """Validate a token and return org name + role (public endpoint).

    Returns ``(info_dict, None)`` or ``(None, error_message)``.
    """
    link = db.query(InviteLink).filter(InviteLink.token == token).first()
    if not link:
        return None, 'Invalid invite link'

    error = _check_link_validity(link)
    if error:
        return None, error

    org = db.query(Organization).filter(Organization.id == link.tenant_id).first()
    return {
        'organization_name': org.name if org else 'Unknown',
        'role': link.role,
    }, None


def join_via_invite(db, token, username, email, password):
    """Register a new user via invite token.

    Returns ``(result_dict, None)`` or ``(None, error_message)``.
    """
    link = db.query(InviteLink).filter(InviteLink.token == token).first()
    if not link:
        return None, 'Invalid invite link'

    error = _check_link_validity(link)
    if error:
        return None, error

    # Check email uniqueness (global)
    existing = db.query(User).filter_by(email=email).first()
    if existing:
        return None, 'Email already registered'

    # Check username uniqueness within tenant
    existing_name = (
        db.query(User)
        .filter_by(tenant_id=link.tenant_id, username=username)
        .first()
    )
    if existing_name:
        return None, 'Username already taken in this organization'

    user = User(
        tenant_id=link.tenant_id,
        username=username,
        email=email,
        password_hash=hash_password(password),
        role=link.role,
    )
    db.add(user)

    link.use_count = (link.use_count or 0) + 1
    db.commit()
    db.refresh(user)

    org = db.query(Organization).filter(Organization.id == link.tenant_id).first()

    return {
        'user': {
            'id': str(user.id),
            'tenant_id': str(user.tenant_id),
            'username': user.username,
            'email': user.email,
            'role': user.role,
        },
        'organization': {
            'id': str(org.id),
            'name': org.name,
            'slug': org.slug,
            'plan': org.plan,
            'trial_ends_at': org.trial_ends_at.isoformat() if org.trial_ends_at else None,
            'subscription_status': org.subscription_status,
        },
    }, None


# ---------------------------------------------------------------------------
# Member management (admin)
# ---------------------------------------------------------------------------

def list_members(db):
    """Return all users in the current tenant."""
    users = (
        db.query(User)
        .filter(User.tenant_id == g.tenant_id)
        .order_by(User.created_at.asc())
        .all()
    )
    return [_user_to_dict(u) for u in users]


def update_member_role(db, user_id, new_role):
    """Change a member's role. Cannot change own role.

    Returns ``(user_dict, None)`` or ``(None, error_message)``.
    """
    if str(user_id) == str(g.user_id):
        return None, 'Cannot change your own role'

    user = (
        db.query(User)
        .filter(User.id == user_id, User.tenant_id == g.tenant_id)
        .first()
    )
    if not user:
        return None, 'User not found'

    if new_role not in ('admin', 'user'):
        return None, 'Invalid role'

    user.role = new_role
    db.commit()
    db.refresh(user)
    return _user_to_dict(user), None


def deactivate_member(db, user_id):
    """Deactivate a member. Cannot deactivate self.

    Returns ``(user_dict, None)`` or ``(None, error_message)``.
    """
    if str(user_id) == str(g.user_id):
        return None, 'Cannot deactivate yourself'

    user = (
        db.query(User)
        .filter(User.id == user_id, User.tenant_id == g.tenant_id)
        .first()
    )
    if not user:
        return None, 'User not found'

    user.is_active = False
    db.commit()
    db.refresh(user)
    return _user_to_dict(user), None


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _link_to_dict(link):
    return {
        'id': str(link.id),
        'token': link.token,
        'role': link.role,
        'max_uses': link.max_uses,
        'use_count': link.use_count or 0,
        'expires_at': link.expires_at.isoformat() if link.expires_at else None,
        'is_active': link.is_active,
        'created_at': link.created_at.isoformat() if link.created_at else None,
    }


def _user_to_dict(user):
    return {
        'id': str(user.id),
        'username': user.username,
        'email': user.email,
        'role': user.role,
        'is_active': user.is_active,
        'last_login_at': user.last_login_at.isoformat() if user.last_login_at else None,
        'created_at': user.created_at.isoformat() if user.created_at else None,
    }


def _check_link_validity(link):
    """Return an error message if the link is not valid, else None."""
    if not link.is_active:
        return 'This invite link has been revoked'
    if link.expires_at and datetime.now(timezone.utc) > link.expires_at:
        return 'This invite link has expired'
    if link.max_uses is not None and (link.use_count or 0) >= link.max_uses:
        return 'This invite link has reached its usage limit'
    return None
