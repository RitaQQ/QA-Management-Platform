"""
Authentication routes — register, login, token refresh, and profile.
"""
from flask import Blueprint, request, jsonify, g
import jwt as pyjwt

from services.user_service import register, login
from services import member_service
from middleware.auth import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    _get_jwt_secret,
    JWT_ALGORITHM,
)

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


# ---------------------------------------------------------------------------
# POST /api/auth/register
# ---------------------------------------------------------------------------

@auth_bp.route('/register', methods=['POST'])
def register_route():
    """Create a new organization + admin user and return JWT tokens."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    required = ['org_name', 'username', 'email', 'password']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400

    if len(data['password']) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400

    result, error = register(
        data['org_name'], data['username'], data['email'], data['password'],
    )
    if error:
        return jsonify({'error': error}), 400

    user = result['user']
    org = result['organization']

    access_token = create_access_token(user['id'], org['id'], user['role'])
    refresh_token = create_refresh_token(user['id'], org['id'])

    return jsonify({
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': user,
        'organization': org,
    }), 201


# ---------------------------------------------------------------------------
# POST /api/auth/login
# ---------------------------------------------------------------------------

@auth_bp.route('/login', methods=['POST'])
def login_route():
    """Authenticate an existing user and return JWT tokens."""
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'error': 'Email and password required'}), 400

    user, error = login(data['email'], data['password'])
    if error:
        return jsonify({'error': error}), 401

    access_token = create_access_token(user['id'], user['tenant_id'], user['role'])
    refresh_token = create_refresh_token(user['id'], user['tenant_id'])

    return jsonify({
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': user,
    }), 200


# ---------------------------------------------------------------------------
# POST /api/auth/refresh
# ---------------------------------------------------------------------------

@auth_bp.route('/refresh', methods=['POST'])
def refresh_route():
    """Exchange a valid refresh token for a new access token."""
    data = request.get_json()
    if not data or not data.get('refresh_token'):
        return jsonify({'error': 'Refresh token required'}), 400

    try:
        payload = pyjwt.decode(
            data['refresh_token'], _get_jwt_secret(), algorithms=[JWT_ALGORITHM],
        )
        if payload.get('type') != 'refresh':
            return jsonify({'error': 'Invalid token type'}), 401
    except pyjwt.ExpiredSignatureError:
        return jsonify({'error': 'Refresh token expired'}), 401
    except pyjwt.InvalidTokenError:
        return jsonify({'error': 'Invalid refresh token'}), 401

    # Look up current role from the database
    from database.session import SessionLocal
    from database.models import User
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(id=payload['user_id']).first()
        if not user:
            return jsonify({'error': 'User not found'}), 401
        role = user.role
    finally:
        db.close()

    access_token = create_access_token(
        payload['user_id'], payload['tenant_id'], role,
    )
    return jsonify({'access_token': access_token}), 200


# ---------------------------------------------------------------------------
# GET /api/auth/invite/<token> -- Validate invite token (public)
# ---------------------------------------------------------------------------

@auth_bp.route('/invite/<token>', methods=['GET'])
def validate_invite(token):
    """Validate an invite token and return the organisation name + role."""
    from database.session import SessionLocal
    db = SessionLocal()
    try:
        info, error = member_service.validate_invite_token(db, token)
        if error:
            return jsonify({'error': error}), 400
        return jsonify({'data': info}), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# POST /api/auth/join -- Join organisation via invite token (public)
# ---------------------------------------------------------------------------

@auth_bp.route('/join', methods=['POST'])
def join_route():
    """Register a new user via an invite link and return JWT tokens."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    required = ['token', 'username', 'email', 'password']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400

    if len(data['password']) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400

    from database.session import SessionLocal
    db = SessionLocal()
    try:
        result, error = member_service.join_via_invite(
            db, data['token'], data['username'], data['email'], data['password'],
        )
        if error:
            return jsonify({'error': error}), 400

        user = result['user']
        org = result['organization']

        access_token = create_access_token(user['id'], org['id'], user['role'])
        refresh_token = create_refresh_token(user['id'], org['id'])

        return jsonify({
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': user,
            'organization': org,
        }), 201
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /api/auth/me
# ---------------------------------------------------------------------------

@auth_bp.route('/me', methods=['GET'])
@jwt_required
def me_route():
    """Return the authenticated user's profile and organization info."""
    from database.session import SessionLocal
    from database.models import User, Organization
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(id=g.user_id).first()
        org = db.query(Organization).filter_by(id=g.tenant_id).first()
        return jsonify({
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
                'trial_ends_at': org.trial_ends_at.isoformat() if org.trial_ends_at else None,
                'subscription_status': org.subscription_status,
            },
        }), 200
    finally:
        db.close()
