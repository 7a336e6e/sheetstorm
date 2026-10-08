"""Feature fixtures, one module per feature: tests/fixtures/<feature>.py.

Every public module in this package is registered through ``pytest_plugins``
in tests/conftest.py automatically, so adding a module never needs a conftest
edit. Fixture names must be unique across modules: prefix them with the
feature (e.g. ``evidence_item``, ``decision_factory``). Shared helpers
(make_user, fresh_user, platform_org, platform_admin, make_incident, auth,
users, org_a/org_b) stay in conftest.py.
"""
