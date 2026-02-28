"""
JWT authentication middleware.

Provides token creation helpers and Flask decorator functions
for protecting routes with Bearer-token-based authentication.
"""
import os
from functools import wraps
from datetime import datetime, timedelta, timezone

import jwt
from flask import request, jsonify, g

from database.session import SessionLocal
from database.models import Organization

JWT_ALGORITHM = 'HS256'


def _get_jwt_secret():
    secret = os.environ.get('JWT_SECRET')
    if not secret:
        raise RuntimeError('JWT_SECRET environment variable is required')
    return secret

ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
REFRESH_TOKEN_EXPIRES = timedelta(days=30)


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------

def create_access_token(user_id, tenant_id, role):
    """Create a short-lived access token."""
    payload = {
        'user_id': str(user_id),
        'tenant_id': str(tenant_id),
        'role': role,
        'exp': datetime.now(timezone.utc) + ACCESS_TOKEN_EXPIRES,
        'type': 'access',
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id, tenant_id):
    """Create a long-lived refresh token (no role claim)."""
    payload = {
        'user_id': str(user_id),
        'tenant_id': str(tenant_id),
        'exp': datetime.now(timezone.utc) + REFRESH_TOKEN_EXPIRES,
        'type': 'refresh',
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm=JWT_ALGORITHM)


# ---------------------------------------------------------------------------
# Route decorators
# ---------------------------------------------------------------------------

def jwt_required(f):
    """Require a valid JWT access token in the ``Authorization: Bearer`` header.

    On success the decoded claims are stored in ``flask.g``:
    - ``g.user_id``
    - ``g.tenant_id``
    - ``g.role``

    Trial expiration is checked for write operations (non-GET/HEAD/OPTIONS).
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]

        if not token:
            return jsonify({'error': 'Missing authorization token'}), 401

        try:
            payload = jwt.decode(token, _get_jwt_secret(), algorithms=[JWT_ALGORITHM])
            if payload.get('type') != 'access':
                return jsonify({'error': 'Invalid token type'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401

        # Check trial expiration for write operations
        db = SessionLocal()
        try:
            org = db.query(Organization).filter_by(id=payload['tenant_id']).first()
            if org and org.subscription_status == 'trialing':
                if org.trial_ends_at and datetime.now(timezone.utc) > org.trial_ends_at:
                    org.subscription_status = 'expired'
                    db.commit()

            if org and org.subscription_status == 'expired':
                if request.method not in ('GET', 'HEAD', 'OPTIONS'):
                    return jsonify({'error': 'Trial expired. Please upgrade to continue.'}), 403

            g.user_id = payload['user_id']
            g.tenant_id = payload['tenant_id']
            g.role = payload['role']
        finally:
            db.close()

        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Require a valid JWT token **and** ``role == 'admin'``."""
    @wraps(f)
    @jwt_required
    def decorated(*args, **kwargs):
        if g.role != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated
