"""
Member management routes -- list members, manage roles, invite links.

All endpoints require JWT authentication; invite-link CRUD requires admin.
"""
from flask import Blueprint, request, jsonify

from middleware.auth import jwt_required, admin_required
from database.session import SessionLocal
from services import member_service as svc

members_bp = Blueprint('members', __name__, url_prefix='/api/members')


# ---------------------------------------------------------------------------
# GET /api/members -- List organisation members
# ---------------------------------------------------------------------------

@members_bp.route('', methods=['GET'])
@jwt_required
def list_members():
    db = SessionLocal()
    try:
        data = svc.list_members(db)
        return jsonify({'data': data}), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# PUT /api/members/<id>/role -- Update member role
# ---------------------------------------------------------------------------

@members_bp.route('/<user_id>/role', methods=['PUT'])
@admin_required
def update_role(user_id):
    body = request.get_json()
    if not body or not body.get('role'):
        return jsonify({'error': 'role is required'}), 400

    db = SessionLocal()
    try:
        result, error = svc.update_member_role(db, user_id, body['role'])
        if error:
            code = 404 if 'not found' in error.lower() else 400
            return jsonify({'error': error}), code
        return jsonify({'data': result}), 200
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# POST /api/members/<id>/deactivate -- Deactivate member
# ---------------------------------------------------------------------------

@members_bp.route('/<user_id>/deactivate', methods=['POST'])
@admin_required
def deactivate_member(user_id):
    db = SessionLocal()
    try:
        result, error = svc.deactivate_member(db, user_id)
        if error:
            code = 404 if 'not found' in error.lower() else 400
            return jsonify({'error': error}), code
        return jsonify({'data': result}), 200
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# POST /api/members/invite-links -- Create invite link (admin)
# ---------------------------------------------------------------------------

@members_bp.route('/invite-links', methods=['POST'])
@admin_required
def create_invite_link():
    body = request.get_json() or {}

    db = SessionLocal()
    try:
        result = svc.create_invite_link(
            db,
            role=body.get('role', 'user'),
            max_uses=body.get('max_uses'),
            expires_hours=body.get('expires_hours'),
        )
        return jsonify({'data': result}), 201
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /api/members/invite-links -- List invite links (admin)
# ---------------------------------------------------------------------------

@members_bp.route('/invite-links', methods=['GET'])
@admin_required
def list_invite_links():
    db = SessionLocal()
    try:
        data = svc.list_invite_links(db)
        return jsonify({'data': data}), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# DELETE /api/members/invite-links/<id> -- Revoke invite link (admin)
# ---------------------------------------------------------------------------

@members_bp.route('/invite-links/<link_id>', methods=['DELETE'])
@admin_required
def revoke_invite_link(link_id):
    db = SessionLocal()
    try:
        success = svc.revoke_invite_link(db, link_id)
        if not success:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'message': 'Revoked'}), 200
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()
