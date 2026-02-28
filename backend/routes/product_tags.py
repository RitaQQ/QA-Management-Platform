"""
Product tag management routes -- CRUD for product tags.

All endpoints require JWT authentication and are tenant-scoped.
"""
from flask import Blueprint, request, jsonify

from middleware.auth import jwt_required
from database.session import SessionLocal
from services import product_tag_service as svc

product_tags_bp = Blueprint('product_tags', __name__, url_prefix='/api/product-tags')


# ---------------------------------------------------------------------------
# GET /api/product-tags -- List all tags
# ---------------------------------------------------------------------------

@product_tags_bp.route('', methods=['GET'])
@jwt_required
def list_tags():
    """Return all product tags for the current tenant."""
    db = SessionLocal()
    try:
        data = svc.list_tags(db)
        return jsonify({'data': data}), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# POST /api/product-tags -- Create tag
# ---------------------------------------------------------------------------

@product_tags_bp.route('', methods=['POST'])
@jwt_required
def create_tag():
    """Create a new product tag."""
    body = request.get_json()
    if not body:
        return jsonify({'error': 'Request body required'}), 400

    db = SessionLocal()
    try:
        result, error = svc.create_tag(db, body)
        if error:
            return jsonify({'error': error}), 400
        return jsonify({'data': result}), 201
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


# ---------------------------------------------------------------------------
# PUT /api/product-tags/<id> -- Update tag
# ---------------------------------------------------------------------------

@product_tags_bp.route('/<int:tag_id>', methods=['PUT'])
@jwt_required
def update_tag(tag_id):
    """Update an existing product tag."""
    body = request.get_json()
    if not body:
        return jsonify({'error': 'Request body required'}), 400

    db = SessionLocal()
    try:
        result, error = svc.update_tag(db, tag_id, body)
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
# DELETE /api/product-tags/<id> -- Delete tag
# ---------------------------------------------------------------------------

@product_tags_bp.route('/<int:tag_id>', methods=['DELETE'])
@jwt_required
def delete_tag(tag_id):
    """Delete a product tag."""
    db = SessionLocal()
    try:
        success = svc.delete_tag(db, tag_id)
        if not success:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'message': 'Deleted'}), 200
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()
