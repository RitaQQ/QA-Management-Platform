"""
Application factory for the QA Platform backend.

Creates and configures a Flask application instance.
Used by tests and production entry points alike.
"""
from flask import Flask
from flask_cors import CORS


def create_app(testing=False):
    """Build and return a configured Flask application.

    Parameters
    ----------
    testing : bool
        When *True*, sets ``app.config['TESTING']`` so that error handlers
        propagate exceptions instead of returning generic error pages.
    """
    app = Flask(__name__)
    app.config['TESTING'] = testing
    CORS(app)

    # ---- Register blueprints ------------------------------------------------
    from routes.auth import auth_bp
    app.register_blueprint(auth_bp)

    from routes.api_monitor import api_monitor_bp
    app.register_blueprint(api_monitor_bp)

    from routes.test_cases import test_cases_bp
    app.register_blueprint(test_cases_bp)

    from routes.product_tags import product_tags_bp
    app.register_blueprint(product_tags_bp)

    from routes.test_projects import test_projects_bp
    app.register_blueprint(test_projects_bp)

    from routes.coverage import coverage_bp
    app.register_blueprint(coverage_bp)

    from routes.jira import jira_bp
    app.register_blueprint(jira_bp)

    from routes.reports import reports_bp
    app.register_blueprint(reports_bp)

    from routes.notifications import notifications_bp
    app.register_blueprint(notifications_bp)

    from routes.members import members_bp
    app.register_blueprint(members_bp)

    # ---- Health check -------------------------------------------------------
    @app.route('/health')
    def health():
        return {'status': 'ok'}

    # ---- Tenant isolation test routes (temporary, pre-Task-6) ---------------
    _register_tenant_test_routes(app)

    return app


def _register_tenant_test_routes(app):
    """Register temporary routes that demonstrate tenant data isolation.

    These will be replaced by full CRUD blueprints in later tasks.  They
    exist so that ``tests/test_tenant_isolation.py`` has real HTTP
    endpoints to exercise.
    """
    from flask import request as flask_request
    from middleware.auth import jwt_required
    from middleware.tenant import tenant_filter, set_tenant_fields
    from database.session import SessionLocal
    from database.models import TestCase

    @app.route('/api/test-isolation/cases', methods=['GET'])
    @jwt_required
    def list_cases_isolated():
        db = SessionLocal()
        try:
            cases = tenant_filter(db.query(TestCase), TestCase).all()
            return {
                'data': [
                    {'id': c.id, 'title': c.title, 'tc_id': c.tc_id}
                    for c in cases
                ]
            }
        finally:
            db.close()

    @app.route('/api/test-isolation/cases', methods=['POST'])
    @jwt_required
    def create_case_isolated():
        data = flask_request.get_json()
        db = SessionLocal()
        try:
            count = tenant_filter(db.query(TestCase), TestCase).count()
            tc_id = f"TC{count + 1:05d}"

            case = TestCase(
                tc_id=tc_id,
                title=data['title'],
                priority=data.get('priority', 'medium'),
            )
            set_tenant_fields(case)
            db.add(case)
            db.commit()
            return {'id': case.id, 'title': case.title, 'tc_id': case.tc_id}, 201
        except Exception as e:
            db.rollback()
            return {'error': str(e)}, 400
        finally:
            db.close()

    @app.route('/api/test-isolation/cases/<int:case_id>', methods=['PUT'])
    @jwt_required
    def update_case_isolated(case_id):
        data = flask_request.get_json()
        db = SessionLocal()
        try:
            case = (
                tenant_filter(db.query(TestCase), TestCase)
                .filter_by(id=case_id)
                .first()
            )
            if not case:
                return {'error': 'Not found'}, 404
            case.title = data.get('title', case.title)
            db.commit()
            return {'id': case.id, 'title': case.title}
        finally:
            db.close()

    @app.route('/api/test-isolation/cases/<int:case_id>', methods=['DELETE'])
    @jwt_required
    def delete_case_isolated(case_id):
        db = SessionLocal()
        try:
            case = (
                tenant_filter(db.query(TestCase), TestCase)
                .filter_by(id=case_id)
                .first()
            )
            if not case:
                return {'error': 'Not found'}, 404
            db.delete(case)
            db.commit()
            return '', 204
        finally:
            db.close()
