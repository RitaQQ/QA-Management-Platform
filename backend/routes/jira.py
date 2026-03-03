"""
Jira integration routes -- API Token connection, issue management, and webhook handler.

All endpoints except the webhook require JWT authentication.
The webhook endpoint is unauthenticated because Jira calls it externally.
"""
from flask import Blueprint, request, jsonify, g

from middleware.auth import jwt_required
from database.models import Organization
from database.session import SessionLocal
from services import jira_service as svc
from services.jira_service import DEFAULT_BUG_TITLE_TEMPLATE, DEFAULT_BUG_DESCRIPTION_TEMPLATE

jira_bp = Blueprint('jira', __name__, url_prefix='/api/jira')


# ---------------------------------------------------------------------------
# POST /api/jira/connect -- Save API Token credentials
# ---------------------------------------------------------------------------

@jira_bp.route('/connect', methods=['POST'])
@jwt_required
def connect():
    """Save Jira API Token credentials for the current tenant.

    Expects JSON body with ``site_url``, ``email``, and ``api_token``.
    """
    body = request.get_json()
    if not body:
        return jsonify({'error': 'Request body required'}), 400

    site_url = body.get('site_url')
    email = body.get('email')
    api_token = body.get('api_token')

    if not site_url or not email or not api_token:
        return jsonify({'error': 'site_url, email, and api_token are required'}), 400

    db = SessionLocal()
    try:
        result, error = svc.connect_with_token(db, site_url, email, api_token)
        if error:
            return jsonify({'error': error}), 400
        return jsonify({'data': result}), 200
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# POST /api/jira/test-connection -- Test stored credentials
# ---------------------------------------------------------------------------

@jira_bp.route('/test-connection', methods=['POST'])
@jwt_required
def test_connection():
    """Test that the stored Jira credentials are valid."""
    db = SessionLocal()
    try:
        result, error = svc.test_connection(db)
        if error:
            return jsonify({'error': error}), 400
        return jsonify({'data': result}), 200
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# POST /api/jira/disconnect -- Clear all credentials
# ---------------------------------------------------------------------------

@jira_bp.route('/disconnect', methods=['POST'])
@jwt_required
def jira_disconnect():
    """Clear all Jira credentials for the current tenant."""
    db = SessionLocal()
    try:
        result, error = svc.disconnect(db)
        if error:
            return jsonify({'error': error}), 400
        return jsonify({'data': result}), 200
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /api/jira/status -- Check connection status
# ---------------------------------------------------------------------------

@jira_bp.route('/status', methods=['GET'])
@jwt_required
def status():
    """Return the current Jira connection status for the tenant."""
    db = SessionLocal()
    try:
        result = svc.get_connection_status(db)
        return jsonify({'data': result}), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /api/jira/projects -- List Jira projects
# ---------------------------------------------------------------------------

@jira_bp.route('/projects', methods=['GET'])
@jwt_required
def list_projects():
    """List available Jira projects from the connected site."""
    db = SessionLocal()
    try:
        result, error = svc.list_projects(db)
        if error:
            return jsonify({'error': error}), 400
        return jsonify({'data': result}), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# POST /api/jira/create-issue -- Create issue from test result
# ---------------------------------------------------------------------------

@jira_bp.route('/create-issue', methods=['POST'])
@jwt_required
def create_issue():
    """Create a Jira issue from a failed test result.

    Expects JSON body with ``test_result_id``, ``project_key``, and
    optional ``issue_type`` (defaults to ``'Bug'``).
    """
    body = request.get_json()
    if not body:
        return jsonify({'error': 'Request body required'}), 400

    test_result_id = body.get('test_result_id')
    project_key = body.get('project_key')
    if not test_result_id or not project_key:
        return jsonify({'error': 'test_result_id and project_key are required'}), 400

    issue_type = body.get('issue_type', 'Bug')

    db = SessionLocal()
    try:
        result, error = svc.create_issue_from_test_result(
            db, test_result_id, project_key, issue_type,
        )
        if error:
            return jsonify({'error': error}), 400
        return jsonify({'data': result}), 201
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# POST /api/jira/webhook -- Jira webhook (NO AUTH)
# ---------------------------------------------------------------------------

@jira_bp.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming Jira webhook events.

    This endpoint does **not** require authentication because Jira
    calls it externally.  It processes ``jira:issue_updated`` events
    to synchronize issue status back to local records.
    """
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({'error': 'Invalid payload'}), 400

    db = SessionLocal()
    try:
        result, error = svc.handle_webhook(db, payload)
        if error:
            return jsonify({'error': error}), 400
        return jsonify({'data': result}), 200
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# POST /api/jira/sync/<link_id> -- Manual sync single link
# ---------------------------------------------------------------------------

@jira_bp.route('/sync/<int:link_id>', methods=['POST'])
@jwt_required
def sync_link(link_id):
    """Manually synchronize the status of a single Jira issue link."""
    db = SessionLocal()
    try:
        result, error = svc.sync_issue_status(db, link_id)
        if error:
            return jsonify({'error': error}), 404 if error == 'Link not found' else 400
        return jsonify({'data': result}), 200
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /api/jira/project-links/<project_id> -- Get links for a test project
# ---------------------------------------------------------------------------

@jira_bp.route('/project-links/<int:project_id>', methods=['GET'])
@jwt_required
def project_links(project_id):
    """Return all Jira issue links associated with a test project."""
    db = SessionLocal()
    try:
        result, error = svc.get_issue_links_for_project(db, project_id)
        if error:
            return jsonify({'error': error}), 404 if error == 'Project not found' else 400
        return jsonify({'data': result}), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /api/jira/bug-template -- Return bug title/description templates
# ---------------------------------------------------------------------------

@jira_bp.route('/bug-template', methods=['GET'])
@jwt_required
def get_bug_template():
    """Return the org's Jira bug title/description templates and available placeholders."""
    db = SessionLocal()
    try:
        org = db.query(Organization).filter_by(id=g.tenant_id).first()
        return jsonify({'data': {
            'title_template': org.jira_bug_title_template if org else None,
            'description_template': org.jira_bug_description_template if org else None,
            'available_placeholders': [
                {'key': 'tc_id', 'label': 'TC ID', 'example': 'AUTH-001'},
                {'key': 'title', 'label': 'Test Case Title', 'example': 'Login Feature Test'},
                {'key': 'user_role', 'label': 'User Role', 'example': 'Admin'},
                {'key': 'feature_description', 'label': 'Feature Description', 'example': 'User authentication'},
                {'key': 'acceptance_criteria', 'label': 'Acceptance Criteria', 'example': 'Should login successfully'},
                {'key': 'test_notes', 'label': 'Test Notes', 'example': 'Field not accepting input'},
                {'key': 'known_issues', 'label': 'Known Issues', 'example': 'DB timeout'},
                {'key': 'status', 'label': 'Test Result Status', 'example': 'fail'},
                {'key': 'project_key', 'label': 'Jira Project Key', 'example': 'PROJ'},
            ],
            'default_title': DEFAULT_BUG_TITLE_TEMPLATE,
            'default_description': DEFAULT_BUG_DESCRIPTION_TEMPLATE,
        }}), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# PUT /api/jira/bug-template -- Save bug title/description templates
# ---------------------------------------------------------------------------

@jira_bp.route('/bug-template', methods=['PUT'])
@jwt_required
def update_bug_template():
    """Save the org's Jira bug title/description templates."""
    body = request.get_json()
    if not body:
        return jsonify({'error': 'Request body required'}), 400

    db = SessionLocal()
    try:
        org = db.query(Organization).filter_by(id=g.tenant_id).first()
        if not org:
            return jsonify({'error': 'Organization not found'}), 404

        title = (body.get('title_template') or '').strip() or None
        description = (body.get('description_template') or '').strip() or None

        org.jira_bug_title_template = title
        org.jira_bug_description_template = description
        db.commit()

        return jsonify({'data': {
            'title_template': org.jira_bug_title_template,
            'description_template': org.jira_bug_description_template,
        }}), 200
    finally:
        db.close()
