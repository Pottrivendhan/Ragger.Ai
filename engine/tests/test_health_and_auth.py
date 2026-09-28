"""Tests for health endpoints and token authentication."""

import pytest
from httpx import ASGITransport, AsyncClient
from ragger_engine.core.config import settings
from ragger_engine.main import create_app


@pytest.fixture(autouse=True)
def configure_test_token():
    """Configure a known test token for tests."""
    original_token = settings.ragger_api_token
    settings.ragger_api_token = "test-secret-token-abcdef123456"
    yield
    settings.ragger_api_token = original_token


@pytest.mark.asyncio
async def test_unauthenticated_liveness_probe():
    """GET /health must succeed without any Authorization header."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "ragger-engine"
        assert "version" in data


@pytest.mark.asyncio
async def test_protected_health_missing_token():
    """GET /api/v1/health must return 401 when token is missing."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 401
        data = response.json()
        assert data["code"] == "AUTH_MISSING_TOKEN"


@pytest.mark.asyncio
async def test_protected_health_invalid_token():
    """GET /api/v1/health must return 401 when token is wrong."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        response = await client.get(
            "/api/v1/health",
            headers={"Authorization": "Bearer wrong-token-value"}
        )
        assert response.status_code == 401
        data = response.json()
        assert data["code"] == "AUTH_INVALID_TOKEN"


@pytest.mark.asyncio
async def test_protected_health_valid_token():
    """GET /api/v1/health must return 200 with valid token."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        response = await client.get(
            "/api/v1/health",
            headers={"Authorization": "Bearer test-secret-token-abcdef123456"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["authenticated"] is True
        assert isinstance(data["process_id"], int)


@pytest.mark.asyncio
async def test_runtime_endpoint_does_not_leak_secrets():
    """GET /api/v1/runtime must return diagnostics and NOT include the token."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        response = await client.get(
            "/api/v1/runtime",
            headers={"Authorization": "Bearer test-secret-token-abcdef123456"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "python_version" in data
        assert "platform" in data
        assert "process_id" in data
        # Ensure secret token is NOT in payload
        assert "token" not in data
        assert "test-secret-token-abcdef123456" not in str(data)
