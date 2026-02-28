"""
Coverage routes -- API-TestCase cross-linking, dashboard, and alerts.

All endpoints require JWT authentication and are tenant-scoped.
"""
from flask import Blueprint, request, jsonify

from middleware.auth import jwt_required
from database.session import SessionLocal
from services import coverage_service as svc

coverage_bp = Blueprint('coverage', __name__, url_prefix='/api/coverage')


# ---------------------------------------------------------------------------
# POST /api/coverage/links -- Create link
# ---------------------------------------------------------------------------

@coverage_bp.route('/links', methods=['POST'])
@jwt_required
def create_link():
    """Create a link between an API endpoint and a test case."""
    body = request.get_json()
    if not body:
        return jsonify({'error': 'Request body required'}), 400

    api_id = body.get('api_id')
    test_case_id = body.get('test_case_id')
    if not api_id or not test_case_id:
        return jsonify({'error': 'api_id and test_case_id are required'}), 400

    db = SessionLocal()
    try:
        result, error = svc.link_api_to_test_case(
            db, api_id, test_case_id, link_type=body.get('link_type', 'covers'),
        )
        if error:
            status_code = 409 if 'already exists' in error.lower() else 404
            return jsonify({'error': error}), status_code
        return jsonify({'data': result}), 201
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# DELETE /api/coverage/links -- Remove link
# ---------------------------------------------------------------------------

@coverage_bp.route('/links', methods=['DELETE'])
@jwt_required
def remove_link():
    """Remove a link between an API endpoint and a test case."""
    body = request.get_json()
    if not body:
        return jsonify({'error': 'Request body required'}), 400

    api_id = body.get('api_id')
    test_case_id = body.get('test_case_id')
    if not api_id or not test_case_id:
        return jsonify({'error': 'api_id and test_case_id are required'}), 400

    db = SessionLocal()
    try:
        result, error = svc.unlink_api_from_test_case(db, api_id, test_case_id)
        if error:
            return jsonify({'error': error}), 404
        return jsonify({'data': result}), 200
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /api/coverage/dashboard -- Coverage overview
# ---------------------------------------------------------------------------

@coverage_bp.route('/dashboard', methods=['GET'])
@jwt_required
def coverage_dashboard():
    """Return coverage overview for the current tenant."""
    db = SessionLocal()
    try:
        data = svc.get_coverage_dashboard(db)
        return jsonify({'data': data}), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /api/coverage/api/<id>/cases -- API's linked test cases
# ---------------------------------------------------------------------------

@coverage_bp.route('/api/<int:api_id>/cases', methods=['GET'])
@jwt_required
def api_linked_cases(api_id):
    """Return an API endpoint with its linked test cases."""
    db = SessionLocal()
    try:
        result, error = svc.get_api_with_linked_cases(db, api_id)
        if error:
            return jsonify({'error': error}), 404
        return jsonify({'data': result}), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /api/coverage/case/<id>/apis -- Test case's linked APIs
# ---------------------------------------------------------------------------

@coverage_bp.route('/case/<int:case_id>/apis', methods=['GET'])
@jwt_required
def case_linked_apis(case_id):
    """Return a test case with its linked API endpoints."""
    db = SessionLocal()
    try:
        result, error = svc.get_case_with_linked_apis(db, case_id)
        if error:
            return jsonify({'error': error}), 404
        return jsonify({'data': result}), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /api/coverage/alerts -- Coverage alerts
# ---------------------------------------------------------------------------

@coverage_bp.route('/alerts', methods=['GET'])
@jwt_required
def coverage_alerts():
    """Return coverage alerts for the current tenant."""
    db = SessionLocal()
    try:
        data = svc.get_alerts(db)
        return jsonify({'data': data}), 200
    finally:
        db.close()
