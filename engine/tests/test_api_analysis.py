"""API Integration tests for Phase 3 Analyzer endpoints."""

from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient

from ragger_engine.core.config import settings
from ragger_engine.main import create_app

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_SECRET_TOKEN = "test_secret_analyzer_token_12345"


@pytest.fixture(autouse=True)
def configure_test_token():
    orig = settings.ragger_api_token
    settings.ragger_api_token = TEST_SECRET_TOKEN
    yield
    settings.ragger_api_token = orig


@pytest.mark.asyncio
async def test_api_analysis_lifecycle_and_auth():
    """Full API test: ingest file, run analysis, synthesize workspace, verify auth."""
    app = create_app()
    headers = {"Authorization": f"Bearer {TEST_SECRET_TOKEN}"}
    pdf_path = str((FIXTURES_DIR / "sample.pdf").resolve())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        # 1. Ingest via API
        ingest_resp = await client.post(
            "/api/v1/ingestion/ingest",
            json={"file_path": pdf_path},
            headers=headers,
        )
        assert ingest_resp.status_code == 200
        source_id = ingest_resp.json()["source"]["source_id"]

        # 2. Test Unauthenticated Call (Must return 401)
        unauth_resp = await client.post(
            "/api/v1/analysis/file",
            json={"source_id": source_id},
        )
        assert unauth_resp.status_code == 401

        # 3. Test Authenticated Analysis Call
        auth_resp = await client.post(
            "/api/v1/analysis/file",
            json={"source_id": source_id, "provider": "heuristic_offline"},
            headers=headers,
        )
        assert auth_resp.status_code == 200
        profile_data = auth_resp.json()

        assert profile_data["source_id"] == source_id
        assert "structural_facts" in profile_data
        assert "semantic_observations" in profile_data
        assert profile_data["structural_facts"]["heading_depth"] >= 2
        assert profile_data["telemetry"]["requested_provider"] == "heuristic_offline"

        # 4. Test Workspace Synthesis
        ws_resp = await client.post(
            "/api/v1/analysis/workspace",
            json={"workspace_id": "api_test_ws"},
            headers=headers,
        )
        assert ws_resp.status_code == 200
        ws_data = ws_resp.json()
        assert ws_data["total_sources"] >= 1
        assert "modality_distribution" in ws_data

        # 5. Test List Providers
        prov_resp = await client.get("/api/v1/analysis/providers", headers=headers)
        assert prov_resp.status_code == 200
        prov_list = prov_resp.json()
        assert any(p["id"] == "heuristic_offline" for p in prov_list)
        assert any(p["id"] == "ollama" for p in prov_list)
