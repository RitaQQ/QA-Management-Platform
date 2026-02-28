"""
Notification settings routes — get and update email/webhook configuration.

All endpoints require JWT authentication and are tenant-scoped.
"""
from flask import Blueprint, request, jsonify

from middleware.auth import jwt_required
from middleware.tenant import get_tenant_id
from database.session import SessionLocal
from database.models import Organization

notifications_bp = Blueprint(
    'notifications', __name__, url_prefix='/api/notifications',
)


# ---------------------------------------------------------------------------
# GET /api/notifications/settings — Retrieve current notification settings
# ---------------------------------------------------------------------------

@notifications_bp.route('/settings', methods=['GET'])
@jwt_required
def get_notification_settings():
    """Return the notification email and webhook URL for the current tenant."""
    db = SessionLocal()
    try:
        org = db.query(Organization).filter_by(id=get_tenant_id()).first()
        if not org:
            return jsonify({'error': 'Organization not found'}), 404

        return jsonify({
            'data': {
                'notification_email': org.notification_email,
                'notification_webhook_url': org.notification_webhook_url,
            }
        }), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# PUT /api/notifications/settings — Update notification settings
# ---------------------------------------------------------------------------

@notifications_bp.route('/settings', methods=['PUT'])
@jwt_required
def update_notification_settings():
    """Update the notification email and/or webhook URL for the current tenant."""
    body = request.get_json()
    if not body:
        return jsonify({'error': 'Request body required'}), 400

    db = SessionLocal()
    try:
        org = db.query(Organization).filter_by(id=get_tenant_id()).first()
        if not org:
            return jsonify({'error': 'Organization not found'}), 404

        if 'notification_email' in body:
            org.notification_email = body['notification_email']
        if 'notification_webhook_url' in body:
            org.notification_webhook_url = body['notification_webhook_url']

        db.commit()
        db.refresh(org)

        return jsonify({
            'data': {
                'notification_email': org.notification_email,
                'notification_webhook_url': org.notification_webhook_url,
            }
        }), 200
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()
