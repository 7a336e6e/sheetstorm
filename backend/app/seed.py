"""Database seeding script: the default organization and its first admin.

The admin's password comes from ADMIN_PASSWORD. When that is unset, empty or
below the password policy, a random policy-compliant password is generated
and printed ONCE to stdout (never logged, never stored in plaintext). Either
way the admin must change it at first sign-in (`must_change_password`), so
no install keeps a well-known or bootstrap password.

Role permissions are not touched here: system roles are immutable and
`app/permissions.py` (applied by the migrations) is their source of truth.
"""
import os
import sys

from app import db, create_app
from app.models import Organization, User, Role, UserRole

DEFAULT_ADMIN_EMAIL = 'admin@sheetstorm.local'


def seed_all():
    """Seed the database with initial data."""
    # Ensure app context
    try:
        from flask import current_app
        if not current_app:
            raise RuntimeError("No app context")
        _run_seed()
    except (RuntimeError, ImportError):
        print("Initializing app context for seeding...")
        app = create_app()
        with app.app_context():
            _run_seed()


def _announce_generated_password(email, password):
    """Show a generated bootstrap password exactly once (stdout only)."""
    sys.stdout.write(
        "\n"
        "============================================================\n"
        f" Initial administrator: {email}\n"
        f" Generated password (shown once, not stored): {password}\n"
        " You must change it at first sign-in.\n"
        "============================================================\n\n"
    )
    sys.stdout.flush()


def _run_seed(org_slug='default'):
    """Internal seeding logic. Returns the created admin, or None."""
    print("Starting database seeding...")

    # Check if already seeded
    if Organization.query.filter_by(slug=org_slug).first():
        print("Database already seeded, skipping...")
        return None

    admin_role = Role.query.filter(Role.name == 'Administrator', Role.is_system.is_(True),
                                   Role.organization_id.is_(None)).first()
    if not admin_role:
        print("ERROR: Roles not found. Make sure database schema is initialized.")
        return None

    # Create default organization
    print("Creating default organization...")
    org = Organization(
        name='Default Organization',
        slug=org_slug,
        settings={}
    )
    db.session.add(org)
    db.session.flush()

    admin_email = (os.getenv('ADMIN_EMAIL') or DEFAULT_ADMIN_EMAIL).strip().lower()
    admin_password = os.getenv('ADMIN_PASSWORD') or ''
    if admin_password:
        from app.api.v1.endpoints.auth import validate_password
        ok, message = validate_password(admin_password)
        if not ok:
            print(f"WARNING: ADMIN_PASSWORD does not meet the password policy ({message}); "
                  "generating a random password instead.")
            admin_password = ''
    generated = not admin_password
    if generated:
        from app.services.user_lifecycle import generate_password
        admin_password = generate_password(24)

    print(f"Creating admin user: {admin_email}")
    admin = User(
        email=admin_email,
        name='Administrator',
        organization_id=org.id,
        auth_provider='local',
        is_active=True,
        is_verified=True,
        must_change_password=True,
    )
    admin.set_password(admin_password)
    db.session.add(admin)
    db.session.flush()

    # Assign admin role
    user_role = UserRole(
        user_id=admin.id,
        role_id=admin_role.id,
        organization_id=org.id
    )
    db.session.add(user_role)

    db.session.commit()
    print("Database seeding completed!")
    print(f"Admin user created: {admin_email} (password change required at first sign-in)")
    if generated:
        _announce_generated_password(admin_email, admin_password)
    else:
        print("Admin password: the ADMIN_PASSWORD value from your environment.")
    return admin


if __name__ == '__main__':
    seed_all()
