"""
API tests for Phase 4 Recommendation endpoints.
Verifies token authentication, evaluation, approval lifecycle, and Phase 5 verification contract.
"""

from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient

from ragger_engine.core.config import settings
from ragger_engine.main import create_app

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_SECRET_TOKEN = "test_secret_rec_token_12345"


@pytest.fixture(autouse=True)
def configure_test_token():
    orig = settings.ragger_api_token
    settings.ragger_api_token = TEST_SECRET_TOKEN
    yield
    settings.ragger_api_token = orig


@pytest.mark.asyncio
async def test_recommendation_endpoints_auth_required():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        # Unauthenticated calls must return 401
        res1 = await client.get("/api/v1/recommendation/architectures")
        assert res1.status_code == 401

        res2 = await client.post("/api/v1/recommendation/evaluate", json={"workspace_id": "default"})
        assert res2.status_code == 401

        res3 = await client.post("/api/v1/recommendation/approve", json={"workspace_id": "default", "architecture_id": "document_rag"})
        assert res3.status_code == 401

        res4 = await client.get("/api/v1/recommendation/validate-build")
        assert res4.status_code == 401


@pytest.mark.asyncio
async def test_recommendation_architectures_catalog():
    app = create_app()
    headers = {"Authorization": f"Bearer {TEST_SECRET_TOKEN}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        res = await client.get("/api/v1/recommendation/architectures", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 6
        arch_ids = [item["architecture_id"] for item in data]
        assert "document_rag" in arch_ids
        assert "knowledge_rag" in arch_ids
        assert "structured_data_rag" in arch_ids
        assert "hybrid_rag" in arch_ids
        assert "research_rag" in arch_ids
        assert "graph_rag" in arch_ids


@pytest.mark.asyncio
async def test_recommendation_and_approval_api_lifecycle():
    app = create_app()
    headers = {"Authorization": f"Bearer {TEST_SECRET_TOKEN}"}
    pdf_path = str((FIXTURES_DIR / "sample.pdf").resolve())
    xlsx_path = str((FIXTURES_DIR / "sample.xlsx").resolve())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        # 1. Ingest PDF and XLSX
        r_pdf = await client.post("/api/v1/ingestion/ingest", json={"file_path": pdf_path}, headers=headers)
        assert r_pdf.status_code == 200
        src_pdf = r_pdf.json()["source"]["source_id"]

        r_xlsx = await client.post("/api/v1/ingestion/ingest", json={"file_path": xlsx_path}, headers=headers)
        assert r_xlsx.status_code == 200
        src_xlsx = r_xlsx.json()["source"]["source_id"]

        # 2. Analyze both files
        await client.post("/api/v1/analysis/file", json={"source_id": src_pdf, "provider": "heuristic_offline"}, headers=headers)
        await client.post("/api/v1/analysis/file", json={"source_id": src_xlsx, "provider": "heuristic_offline"}, headers=headers)

        # 3. Synthesize workspace
        r_synth = await client.post("/api/v1/analysis/workspace", json={"workspace_id": "default"}, headers=headers)
        assert r_synth.status_code == 200

        # 4. Evaluate recommendation
        r_eval = await client.post("/api/v1/recommendation/evaluate", json={"workspace_id": "default"}, headers=headers)
        assert r_eval.status_code == 200
        rec = r_eval.json()
        assert "recommended_architecture" in rec
        assert rec["confidence_score"] > 0.0
        assert len(rec["detected_signals"]) > 0

        # 5. Query current recommendation
        r_curr = await client.get("/api/v1/recommendation/current", headers=headers)
        assert r_curr.status_code == 200
        assert r_curr.json()["recommendation_id"] == rec["recommendation_id"]

        # 6. Approve configuration
        r_appr = await client.post(
            "/api/v1/recommendation/approve",
            json={
                "workspace_id": "default",
                "architecture_id": rec["recommended_architecture"],
                "is_revision": True,
            },
            headers=headers,
        )
        assert r_appr.status_code == 200
        approved = r_appr.json()
        assert approved["is_frozen"] is True
        assert approved["config_version"] >= 1
        assert approved["config_hash"] is not None

        # 7. Query approved config
        r_get_appr = await client.get("/api/v1/recommendation/approved", headers=headers)
        assert r_get_appr.status_code == 200
        assert r_get_appr.json()["config_id"] == approved["config_id"]

        # 8. Validate Phase 5 build contract
        r_val = await client.get("/api/v1/recommendation/validate-build", headers=headers)
        assert r_val.status_code == 200
        assert r_val.json()["valid"] is True
        assert r_val.json()["config_id"] == approved["config_id"]
