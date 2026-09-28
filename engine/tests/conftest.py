"""
Shared Pytest fixtures for Ragger Engine test suite.
"""

from pathlib import Path
import pytest

from ragger_engine.core.config import settings


@pytest.fixture
def auth_headers():
    original_token = settings.ragger_api_token
    settings.ragger_api_token = "test-secret-token-abcdef123456"
    yield {"Authorization": f"Bearer {settings.ragger_api_token}"}
    settings.ragger_api_token = original_token


@pytest.fixture
def clean_workspace(tmp_path):
    """Creates a pristine temporary workspace directory."""
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws
