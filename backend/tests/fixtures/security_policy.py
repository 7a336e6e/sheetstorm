"""Security-policy fixtures (W3-SEC): set an org's policy directly and put the
platform (default) org's policy back afterwards, so registration stays closed
for every other test."""
import pytest


@pytest.fixture
def set_policy(app, db):
    """set_policy(org, {section: {field: value}}) -> OrganizationSecurityPolicy.

    Writes through the service (validation + enforced_since) with no actor.
    Every touched org's policy is restored after the test."""
    from app.models import Organization, OrganizationSecurityPolicy
    from app.services import security_policy

    saved = {}

    def apply(org, data):
        if org.id not in saved:
            row = OrganizationSecurityPolicy.query.filter_by(organization_id=org.id).first()
            saved[org.id] = dict(row.policy) if row is not None else None
        org = db.session.get(Organization, org.id)
        row, _, _ = security_policy.update_policy(org, data, None)
        db.session.commit()
        return row

    yield apply

    db.session.rollback()
    for org_id, policy in saved.items():
        if db.session.get(Organization, org_id) is None:
            continue
        row = OrganizationSecurityPolicy.query.filter_by(organization_id=org_id).first()
        if policy is None:
            if row is not None:
                db.session.delete(row)
        else:
            row.policy = policy
    db.session.commit()


@pytest.fixture
def open_registration(app, db, set_policy):
    """Open self-registration on the platform org (restored afterwards).
    Returns apply(**provisioning_and_password_overrides)."""
    from app.models import Organization
    slug = app.config.get('PLATFORM_ORG_SLUG', 'default')
    org = Organization.query.filter_by(slug=slug).first()
    if org is None:
        org = Organization(name='Default Organization', slug=slug, settings={})
        db.session.add(org)
        db.session.commit()

    def apply(provisioning=None, password=None):
        data = {'provisioning': {'registration_enabled': True, **(provisioning or {})}}
        if password:
            data['password'] = password
        set_policy(org, data)
        return org
    return apply
