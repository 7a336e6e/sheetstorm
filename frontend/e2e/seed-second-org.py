"""Bootstrap the second E2E organization and its Administrator (idempotent).

There is no API to create organizations, so this runs once inside the backend
container of a TEST stack (never production). Credentials come from the
environment and are never printed:

    export E2E_ORG_B_ADMIN_EMAIL=... E2E_ORG_B_ADMIN_PASSWORD=...
    docker compose exec -T -e E2E_ORG_B_ADMIN_EMAIL -e E2E_ORG_B_ADMIN_PASSWORD \
        backend python - < frontend/e2e/seed-second-org.py

e2e/global-setup.ts then seeds org B's role users through the API as this admin.
"""
import os
import sys

from app import create_app, db
from app.models import Organization, Role, User, UserRole

SLUG = os.environ.get('E2E_ORG_B_SLUG', 'e2e-org-b')

email = os.environ.get('E2E_ORG_B_ADMIN_EMAIL', '').strip().lower()
password = os.environ.get('E2E_ORG_B_ADMIN_PASSWORD', '')
if not email or not password:
    sys.exit('E2E_ORG_B_ADMIN_EMAIL and E2E_ORG_B_ADMIN_PASSWORD must be set')

app = create_app()
with app.app_context():
    from app.api.v1.endpoints.auth import validate_password
    ok, message = validate_password(password)
    if not ok:
        sys.exit(f'E2E_ORG_B_ADMIN_PASSWORD rejected: {message}')

    org = Organization.query.filter_by(slug=SLUG).first()
    if org is None:
        org = Organization(name='E2E Org B', slug=SLUG, settings={})
        db.session.add(org)
        db.session.flush()

    user = User.query.filter_by(email=email).first()
    if user is None:
        user = User(email=email, name='E2E Admin B', organization_id=org.id,
                    auth_provider='local', is_active=True, is_verified=True)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        role = Role.query.filter_by(name='Administrator', is_system=True).one()
        db.session.add(UserRole(user_id=user.id, role_id=role.id, organization_id=org.id))
    elif user.organization_id != org.id:
        sys.exit(f'{email} already exists in another organization; pick another E2E_ORG_B_ADMIN_EMAIL')

    db.session.commit()
    print(f'org {SLUG!r} ready; admin {email}')
