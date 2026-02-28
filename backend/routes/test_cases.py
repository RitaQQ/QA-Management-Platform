"""
Test case management routes -- CRUD, CSV export, and CSV import.

All endpoints require JWT authentication and are tenant-scoped.
"""
from flask import Blueprint, request, jsonify, Response

from middleware.auth import jwt_required
from database.session import SessionLocal
from services import test_case_service as svc

test_cases_bp = Blueprint('test_cases', __name__, url_prefix='/api/test-cases')


# ---------------------------------------------------------------------------
# GET /api/test-cases -- List test cases
# ---------------------------------------------------------------------------

@test_cases_bp.route('', methods=['GET'])
@jwt_required
def list_test_cases():
    """Return all test cases for the current tenant.

    Query parameters: ``priority``, ``status``, ``tag_id``, ``project_id``.
    """
    filters = {
        'priority': request.args.get('priority'),
        'status': request.args.get('status'),
        'tag_id': request.args.get('tag_id', type=int),
        'project_id': request.args.get('project_id', type=int),
    }
    # Remove None values
    filters = {k: v for k, v in filters.items() if v is not None}

    db = SessionLocal()
    try:
        data = svc.list_test_cases(db, filters)
        return jsonify({'data': data}), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# POST /api/test-cases -- Create test case
# ---------------------------------------------------------------------------

@test_cases_bp.route('', methods=['POST'])
@jwt_required
def create_test_case():
    """Create a new test case."""
    body = request.get_json()
    if not body:
        return jsonify({'error': 'Request body required'}), 400

    db = SessionLocal()
    try:
        result, error = svc.create_test_case(db, body)
        if error:
            return jsonify({'error': error}), 400
        return jsonify({'data': result}), 201
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /api/test-cases/next-tc-id -- Next auto TC ID
# ---------------------------------------------------------------------------

@test_cases_bp.route('/next-tc-id', methods=['GET'])
@jwt_required
def next_tc_id():
    """Return the next auto-generated TC ID for pre-filling the form."""
    db = SessionLocal()
    try:
        tc_id = svc.get_next_tc_id(db)
        return jsonify({'data': tc_id}), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /api/test-cases/export-csv -- Export CSV
# ---------------------------------------------------------------------------

@test_cases_bp.route('/export-csv', methods=['GET'])
@jwt_required
def export_csv():
    """Export all tenant test cases as a CSV file download."""
    db = SessionLocal()
    try:
        csv_content = svc.export_csv(db)
        # Prepend UTF-8 BOM so Excel/Numbers can open the file correctly
        bom = '\ufeff'
        return Response(
            bom + csv_content,
            mimetype='text/csv; charset=utf-8',
            headers={
                'Content-Disposition': 'attachment; filename=test_cases.csv',
            },
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# POST /api/test-cases/import-csv -- Import CSV
# ---------------------------------------------------------------------------

@test_cases_bp.route('/import-csv', methods=['POST'])
@jwt_required
def import_csv():
    """Import test cases from an uploaded CSV file.

    Expects a multipart file upload with field name ``file``.
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'No file selected'}), 400

    db = SessionLocal()
    try:
        csv_content = file.read().decode('utf-8')
        result = svc.import_csv(db, csv_content)
        return jsonify({'data': result}), 200
    except UnicodeDecodeError:
        return jsonify({'error': 'File must be UTF-8 encoded'}), 400
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /api/test-cases/<id> -- Get single test case
# ---------------------------------------------------------------------------

@test_cases_bp.route('/<int:case_id>', methods=['GET'])
@jwt_required
def get_test_case(case_id):
    """Return a single test case by ID."""
    db = SessionLocal()
    try:
        result = svc.get_test_case(db, case_id)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'data': result}), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# PUT /api/test-cases/<id> -- Update test case
# ---------------------------------------------------------------------------

@test_cases_bp.route('/<int:case_id>', methods=['PUT'])
@jwt_required
def update_test_case(case_id):
    """Update an existing test case."""
    body = request.get_json()
    if not body:
        return jsonify({'error': 'Request body required'}), 400

    db = SessionLocal()
    try:
        result, error = svc.update_test_case(db, case_id, body)
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
# DELETE /api/test-cases/<id> -- Delete test case
# ---------------------------------------------------------------------------

@test_cases_bp.route('/<int:case_id>', methods=['DELETE'])
@jwt_required
def delete_test_case(case_id):
    """Delete a test case."""
    db = SessionLocal()
    try:
        success = svc.delete_test_case(db, case_id)
        if not success:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'message': 'Deleted'}), 200
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()
