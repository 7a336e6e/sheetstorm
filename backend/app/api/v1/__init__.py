"""API v1 Blueprint"""
from flask import Blueprint

api_bp = Blueprint('api_v1', __name__)

# Import and register endpoint modules
from app.api.v1.endpoints import health
from app.api.v1.endpoints import auth
from app.api.v1.endpoints import users
from app.api.v1.endpoints import incidents
from app.api.v1.endpoints import timeline
from app.api.v1.endpoints import compromised
from app.api.v1.endpoints import iocs
from app.api.v1.endpoints import artifacts
from app.api.v1.endpoints import tasks
from app.api.v1.endpoints import attack_graph
from app.api.v1.endpoints import reports
from app.api.v1.endpoints import integrations
from app.api.v1.endpoints import audit
from app.api.v1.endpoints import notifications
from app.api.v1.endpoints import organization
from app.api.v1.endpoints import teams
from app.api.v1.endpoints import google_drive
