"""Example feature-fixture module (also proves auto-registration works).

Copy this shape for tests/fixtures/<feature>.py: plain pytest fixtures that
may depend on the shared conftest fixtures.
"""
import pytest


@pytest.fixture
def harness_viewer(fresh_user):
    """A freshly created Viewer in org A."""
    return fresh_user('Viewer')
