"""
User service — registration, login, and password utilities.

Handles organization + user creation during registration, authentication,
and bcrypt-based password hashing.
"""
import re
from datetime import datetime, timedelta, timezone

import bcrypt

from database.models import User, Organization
from database.session import SessionLocal


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Return a bcrypt hash of *password*."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """Check *password* against a bcrypt *password_hash*."""
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))


# ---------------------------------------------------------------------------
# Slug generation
# ---------------------------------------------------------------------------

def generate_slug(name: str) -> str:
    """Convert *name* to a URL-friendly slug."""
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    return slug or 'org'


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(org_name: str, username: str, email: str, password: str):
    """Register a new organization with its first admin user.

    Returns ``(result_dict, None)`` on success or ``(None, error_message)``
    on failure.
    """
    db = SessionLocal()
    try:
        # Check email uniqueness (global — not per-tenant)
        existing = db.query(User).filter_by(email=email).first()
        if existing:
            return None, 'Email already registered'

        # Create organization with a unique slug
        base_slug = generate_slug(org_name)
        slug = base_slug
        counter = 1
        while db.query(Organization).filter_by(slug=slug).first():
            slug = f"{base_slug}-{counter}"
            counter += 1

        org = Organization(
            name=org_name,
            slug=slug,
            plan='trial',
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
            subscription_status='trialing',
        )
        db.add(org)
        db.flush()  # materialise org.id

        # Create the first (admin) user
        user = User(
            tenant_id=org.id,
            username=username,
            email=email,
            password_hash=hash_password(password),
            role='admin',
        )
        db.add(user)
        db.commit()

        return {
            'user': {
                'id': str(user.id),
                'username': user.username,
                'email': user.email,
                'role': user.role,
            },
            'organization': {
                'id': str(org.id),
                'name': org.name,
                'slug': org.slug,
                'plan': org.plan,
                'trial_ends_at': org.trial_ends_at.isoformat(),
                'subscription_status': org.subscription_status,
            },
        }, None
    except Exception as e:
        db.rollback()
        return None, str(e)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def login(email: str, password: str):
    """Authenticate a user by email + password.

    Returns ``(user_dict, None)`` on success or ``(None, error_message)``
    on failure.
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email=email).first()
        if not user or not verify_password(password, user.password_hash):
            return None, 'Invalid email or password'
        if not user.is_active:
            return None, 'Account is deactivated'

        user.last_login_at = datetime.now(timezone.utc)
        db.commit()

        return {
            'id': str(user.id),
            'tenant_id': str(user.tenant_id),
            'username': user.username,
            'email': user.email,
            'role': user.role,
        }, None
    except Exception as e:
        db.rollback()
        return None, str(e)
    finally:
        db.close()
