"""
Report generation routes -- PDF and JSON test project reports.

Provides a single endpoint for generating project reports in either
JSON or PDF format based on a query parameter.
"""
from flask import Blueprint, request, jsonify, Response

from middleware.auth import jwt_required
from database.session import SessionLocal
from services import report_service as svc

reports_bp = Blueprint('reports', __name__, url_prefix='/api')


# ---------------------------------------------------------------------------
# GET /api/test-projects/<id>/report -- Generate project report
# ---------------------------------------------------------------------------

@reports_bp.route('/test-projects/<int:project_id>/report', methods=['GET'])
@jwt_required
def get_project_report(project_id):
    """Generate a test project report.

    Query parameters:
    - format: ``json`` (default) or ``pdf``
    """
    fmt = request.args.get('format', 'json').lower()
    if fmt not in ('json', 'pdf'):
        return jsonify({'error': 'Invalid format. Use json or pdf.'}), 400

    db = SessionLocal()
    try:
        result, error = svc.generate_project_report(db, project_id, fmt=fmt)
        if error:
            return jsonify({'error': error}), 404

        if fmt == 'pdf':
            return Response(
                result,
                mimetype='application/pdf',
                headers={
                    'Content-Disposition': f'attachment; filename=report-{project_id}.pdf',
                },
            )

        return jsonify({'data': result}), 200
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()
