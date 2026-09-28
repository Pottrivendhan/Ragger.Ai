"""Tests for FastAPI ingestion endpoints and token authentication."""

import pytest
from pathlib import Path
from httpx import ASGITransport, AsyncClient
from ragger_engine.core.config import settings
from ragger_engine.main import create_app

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def configure_test_token():
    orig = settings.ragger_api_token
    settings.ragger_api_token = "test-ingestion-token-789"
    yield
    settings.ragger_api_token = orig


@pytest.mark.asyncio
async def test_detect_endpoint_auth_and_result():
    app = create_app()
    pdf_file = str((FIXTURES_DIR / "sample.pdf").resolve())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        # 1. Missing token -> 401
        res_unauth = await client.post("/api/v1/ingestion/detect", json={"file_path": pdf_file})
        assert res_unauth.status_code == 401

        # 2. Valid token -> 200 with detected format
        res_auth = await client.post(
            "/api/v1/ingestion/detect",
            json={"file_path": pdf_file},
            headers={"Authorization": "Bearer test-ingestion-token-789"},
        )
        assert res_auth.status_code == 200
        data = res_auth.json()
        assert data["format"] == "pdf"
        assert data["confidence"] >= 0.9


@pytest.mark.asyncio
async def test_ingest_endpoint_full_pipeline():
    app = create_app()
    csv_file = str((FIXTURES_DIR / "sample.csv").resolve())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        # Ingest CSV -> produces DatasetModel
        res = await client.post(
            "/api/v1/ingestion/ingest",
            json={"file_path": csv_file},
            headers={"Authorization": "Bearer test-ingestion-token-789"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["model_type"] == "dataset"
        assert data["source"]["sha256_checksum"] is not None
        assert data["sample"]["sample_type"] == "dataset"
        assert len(data["sample"]["first_rows"]) > 0
        assert data["metrics"]["parser_used"] == "CSVParser"
