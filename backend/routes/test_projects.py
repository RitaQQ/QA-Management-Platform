"""
Test project management routes -- CRUD, case assignment, result tracking, and statistics.

All endpoints require JWT authentication and are tenant-scoped.
"""
from flask import Blueprint, request, jsonify

from middleware.auth import jwt_required
from database.session import SessionLocal
from services import test_project_service as svc

test_projects_bp = Blueprint('test_projects', __name__, url_prefix='/api/test-projects')


# ---------------------------------------------------------------------------
# GET /api/test-projects -- List all projects with stats
# ---------------------------------------------------------------------------

@test_projects_bp.route('', methods=['GET'])
@jwt_required
def list_projects():
    """Return all test projects for the current tenant with summary statistics."""
    db = SessionLocal()
    try:
        data = svc.list_projects(db)
        return jsonify({'data': data}), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# POST /api/test-projects -- Create project
# ---------------------------------------------------------------------------

@test_projects_bp.route('', methods=['POST'])
@jwt_required
def create_project():
    """Create a new test project."""
    body = request.get_json()
    if not body:
        return jsonify({'error': 'Request body required'}), 400

    db = SessionLocal()
    try:
        result, error = svc.create_project(db, body)
        if error:
            return jsonify({'error': error}), 400
        return jsonify({'data': result}), 201
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /api/test-projects/<id> -- Get project detail with cases and results
# ---------------------------------------------------------------------------

@test_projects_bp.route('/<int:project_id>', methods=['GET'])
@jwt_required
def get_project(project_id):
    """Return a single test project with assigned test cases and results."""
    db = SessionLocal()
    try:
        result = svc.get_project(db, project_id)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'data': result}), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# PUT /api/test-projects/<id> -- Update project
# ---------------------------------------------------------------------------

@test_projects_bp.route('/<int:project_id>', methods=['PUT'])
@jwt_required
def update_project(project_id):
    """Update an existing test project."""
    body = request.get_json()
    if not body:
        return jsonify({'error': 'Request body required'}), 400

    db = SessionLocal()
    try:
        result, error = svc.update_project(db, project_id, body)
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
# DELETE /api/test-projects/<id> -- Delete project
# ---------------------------------------------------------------------------

@test_projects_bp.route('/<int:project_id>', methods=['DELETE'])
@jwt_required
def delete_project(project_id):
    """Delete a test project (cascades results, unlinks cases)."""
    db = SessionLocal()
    try:
        success = svc.delete_project(db, project_id)
        if not success:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'message': 'Deleted'}), 200
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# POST /api/test-projects/<id>/assign-cases -- Assign test cases
# ---------------------------------------------------------------------------

@test_projects_bp.route('/<int:project_id>/assign-cases', methods=['POST'])
@jwt_required
def assign_test_cases(project_id):
    """Assign test cases to a project."""
    body = request.get_json()
    if not body or 'test_case_ids' not in body:
        return jsonify({'error': 'test_case_ids is required'}), 400

    db = SessionLocal()
    try:
        result, error = svc.assign_test_cases(db, project_id, body['test_case_ids'])
        if error:
            return jsonify({'error': error}), 404
        return jsonify({'data': result}), 200
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# PUT /api/test-projects/<id>/assign-user -- Assign user to a test case
# ---------------------------------------------------------------------------

@test_projects_bp.route('/<int:project_id>/assign-user', methods=['PUT'])
@jwt_required
def assign_user(project_id):
    """Assign a user to a test case within a project."""
    body = request.get_json()
    if not body or 'test_case_id' not in body:
        return jsonify({'error': 'test_case_id is required'}), 400

    db = SessionLocal()
    try:
        result, error = svc.assign_user_to_case(
            db, project_id, body['test_case_id'], body.get('user_id'),
        )
        if error:
            status_code = 404 if 'not found' in error.lower() else 400
            return jsonify({'error': error}), status_code
        return jsonify({'data': result}), 200
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# PUT /api/test-projects/<id>/results -- Update test result (UPSERT)
# ---------------------------------------------------------------------------

@test_projects_bp.route('/<int:project_id>/results', methods=['PUT'])
@jwt_required
def update_test_result(project_id):
    """Update or create a test result for a case within a project."""
    body = request.get_json()
    if not body:
        return jsonify({'error': 'Request body required'}), 400

    db = SessionLocal()
    try:
        result, error = svc.update_test_result(db, project_id, body)
        if error:
            status_code = 404 if 'not found' in error.lower() else 400
            return jsonify({'error': error}), status_code
        return jsonify({'data': result}), 200
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /api/test-projects/<id>/stats -- Get project statistics
# ---------------------------------------------------------------------------

@test_projects_bp.route('/<int:project_id>/stats', methods=['GET'])
@jwt_required
def get_project_stats(project_id):
    """Return pass/fail/blocked/not_tested statistics for a project."""
    db = SessionLocal()
    try:
        result, error = svc.get_project_stats(db, project_id)
        if error:
            return jsonify({'error': error}), 404
        return jsonify({'data': result}), 200
    finally:
        db.close()
