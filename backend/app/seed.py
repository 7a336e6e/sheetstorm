"""Database seeding script"""
import os
from app import db, create_app
from app.models import Organization, User, Role, UserRole



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

def _run_seed():
    """Internal seeding logic."""
    print("Starting database seeding...")

    # Check if already seeded
    if Organization.query.filter_by(slug='default').first():
        print("Database already seeded, skipping...")
        return

    # Create default organization
    print("Creating default organization...")
    org = Organization(
        name='Default Organization',
        slug='default',
        settings={}
    )
    db.session.add(org)
    db.session.flush()

    # Get admin role
    admin_role = Role.query.filter_by(name='Administrator').first()
    if not admin_role:
        print("ERROR: Roles not found. Make sure database schema is initialized.")
        return
    
    # Ensure admin role has required permissions
    required_perms = ["users:manage", "users:read", "users:create", "users:update", "users:delete"]
    current_perms = set(admin_role.permissions)
    if not all(p in current_perms for p in required_perms):
        print("Updating Administrator permissions...")
        updated_perms = list(current_perms.union(set(required_perms)))
        admin_role.permissions = updated_perms
        db.session.commit()

    # Create admin user
    admin_email = os.getenv('ADMIN_EMAIL', 'admin@sheetstorm.local')
    admin_password = os.getenv('ADMIN_PASSWORD', 'ChangeMe123!')

    print(f"Creating admin user: {admin_email}")
    admin = User(
        email=admin_email,
        name='Administrator',
        organization_id=org.id,
        auth_provider='local',
        is_active=True,
        is_verified=True
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
    print(f"Admin user created: {admin_email}")


if __name__ == '__main__':
    seed_all()

