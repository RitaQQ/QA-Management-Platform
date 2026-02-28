"""
API monitoring routes — CRUD, health checks, history, and uptime.

All endpoints require JWT authentication and are tenant-scoped.
"""
from flask import Blueprint, request, jsonify

from middleware.auth import jwt_required
from database.session import SessionLocal
from services import api_monitor_service as svc

api_monitor_bp = Blueprint('api_monitor', __name__, url_prefix='/api/endpoints')


# ---------------------------------------------------------------------------
# GET /api/endpoints — List all endpoints
# ---------------------------------------------------------------------------

@api_monitor_bp.route('', methods=['GET'])
@jwt_required
def list_endpoints():
    """Return all API endpoints for the current tenant."""
    db = SessionLocal()
    try:
        data = svc.list_endpoints(db)
        return jsonify({'data': data}), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# POST /api/endpoints — Create endpoint
# ---------------------------------------------------------------------------

@api_monitor_bp.route('', methods=['POST'])
@jwt_required
def create_endpoint():
    """Create a new API endpoint."""
    body = request.get_json()
    if not body:
        return jsonify({'error': 'Request body required'}), 400

    db = SessionLocal()
    try:
        result, error = svc.create_endpoint(db, body)
        if error:
            return jsonify({'error': error}), 400
        return jsonify({'data': result}), 201
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /api/endpoints/<id> — Get single endpoint
# ---------------------------------------------------------------------------

@api_monitor_bp.route('/<int:endpoint_id>', methods=['GET'])
@jwt_required
def get_endpoint(endpoint_id):
    """Return a single endpoint by ID."""
    db = SessionLocal()
    try:
        endpoint = svc.get_endpoint(db, endpoint_id)
        if not endpoint:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'data': svc._endpoint_to_dict(endpoint)}), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# PUT /api/endpoints/<id> — Update endpoint
# ---------------------------------------------------------------------------

@api_monitor_bp.route('/<int:endpoint_id>', methods=['PUT'])
@jwt_required
def update_endpoint(endpoint_id):
    """Update an existing endpoint."""
    body = request.get_json()
    if not body:
        return jsonify({'error': 'Request body required'}), 400

    db = SessionLocal()
    try:
        result, error = svc.update_endpoint(db, endpoint_id, body)
        if error:
            status_code = 404 if error == 'Not found' else 400
            return jsonify({'error': error}), status_code
        return jsonify({'data': result}), 200
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# DELETE /api/endpoints/<id> — Delete endpoint
# ---------------------------------------------------------------------------

@api_monitor_bp.route('/<int:endpoint_id>', methods=['DELETE'])
@jwt_required
def delete_endpoint(endpoint_id):
    """Delete an endpoint."""
    db = SessionLocal()
    try:
        success = svc.delete_endpoint(db, endpoint_id)
        if not success:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'message': 'Deleted'}), 200
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# POST /api/endpoints/<id>/check — Trigger health check
# ---------------------------------------------------------------------------

@api_monitor_bp.route('/<int:endpoint_id>/check', methods=['POST'])
@jwt_required
def check_endpoint(endpoint_id):
    """Execute a health check for a single endpoint."""
    db = SessionLocal()
    try:
        result, error = svc.check_endpoint(db, endpoint_id)
        if error:
            return jsonify({'error': error}), 404
        return jsonify({'data': result}), 200
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /api/endpoints/<id>/history — Get check history
# ---------------------------------------------------------------------------

@api_monitor_bp.route('/<int:endpoint_id>/history', methods=['GET'])
@jwt_required
def get_history(endpoint_id):
    """Return check history for an endpoint.

    Query parameters:
    - ``days`` (int, default 1): Number of days of history to return.
    """
    days = request.args.get('days', 1, type=int)
    if days < 1:
        days = 1

    db = SessionLocal()
    try:
        data, error = svc.get_history(db, endpoint_id, days=days)
        if error:
            return jsonify({'error': error}), 404
        return jsonify({'data': data}), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /api/endpoints/<id>/uptime — Get uptime percentage
# ---------------------------------------------------------------------------

@api_monitor_bp.route('/<int:endpoint_id>/uptime', methods=['GET'])
@jwt_required
def get_uptime(endpoint_id):
    """Return uptime percentage for an endpoint.

    Query parameters:
    - ``days`` (int, default 7): Number of days for the calculation.
    """
    days = request.args.get('days', 7, type=int)
    if days < 1:
        days = 1

    db = SessionLocal()
    try:
        data, error = svc.get_uptime(db, endpoint_id, days=days)
        if error:
            return jsonify({'error': error}), 404
        return jsonify({'data': data}), 200
    finally:
        db.close()
