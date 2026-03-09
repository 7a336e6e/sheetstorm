"""Health check endpoint"""
import logging

from flask import jsonify
from app.api.v1 import api_bp
from app import db, redis_client, limiter

logger = logging.getLogger(__name__)


@api_bp.route('/health', methods=['GET'])
@limiter.exempt
def health_check():
    """Health check endpoint for container orchestration."""
    status = {
        'status': 'healthy',
        'services': {
            'api': True,
            'database': False,
            'redis': False
        }
    }

    # Check database
    try:
        db.session.execute(db.text('SELECT 1'))
        status['services']['database'] = True
    except Exception:
        db.session.rollback()
        status['status'] = 'degraded'

    # Check Redis
    try:
        if redis_client:
            redis_client.ping()
            status['services']['redis'] = True
        else:
            logger.warning('Redis client not initialized')
            status['status'] = 'degraded'
    except Exception:
        status['status'] = 'degraded'

    http_status = 200 if status['status'] == 'healthy' else 503
    return jsonify(status), http_status


@api_bp.route('/health/ready', methods=['GET'])
@limiter.exempt
def readiness_check():
    """Readiness check — verifies both database and Redis are reachable."""
    try:
        db.session.execute(db.text('SELECT 1'))
    except Exception:
        db.session.rollback()
        return jsonify({'ready': False, 'reason': 'database unreachable'}), 503

    try:
        if redis_client:
            redis_client.ping()
        else:
            return jsonify({'ready': False, 'reason': 'redis not initialized'}), 503
    except Exception:
        return jsonify({'ready': False, 'reason': 'redis unreachable'}), 503

    return jsonify({'ready': True}), 200


@api_bp.route('/health/live', methods=['GET'])
@limiter.exempt
def liveness_check():
    """Liveness check for Kubernetes."""
    return jsonify({'alive': True}), 200
