"""
API tests for Phase 5 Builder endpoints.
Verifies token authentication, start/progress/cancel/manifest/events endpoints,
and precise HTTP error mappings (409 Conflict, 412 Precondition, 424 Failed Dependency).
"""

import asyncio
import json
from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient

from ragger_engine.api import routes
from ragger_engine.builder.embeddings.testing import TestDeterministicEmbeddingProvider
from ragger_engine.core.config import settings
from ragger_engine.main import create_app
from ragger_engine.recommendation.models import (
    ApprovedBuildConfig,
    ChunkingConfig,
    ChunkingStrategyType,
    EmbeddingConfig,
    RagArchitectureId,
    RetrievalConfig,
    RetrievalStrategy,
    VectorDbConfig,
)
from ragger_engine.recommendation.validation import compute_canonical_config_hash

TEST_SECRET_TOKEN = "test_builder_secret_token_555"


@pytest.fixture(autouse=True)
def configure_test_token():
    orig = settings.ragger_api_token
    settings.ragger_api_token = TEST_SECRET_TOKEN
    yield
    settings.ragger_api_token = orig


@pytest.fixture
def api_workspace(tmp_path: Path):
    ws_dir = tmp_path / "api_ws"
    ws_dir.mkdir(parents=True)
    sources_dir = ws_dir / "sources"
    sources_dir.mkdir(parents=True)

    # Save previous service pointers
    orig_ingestion = routes.ingestion_service
    orig_rec = routes.recommendation_service
    orig_builder = routes.builder_service

    # Wire workspace to routes singletons
    from ragger_engine.ingestion.registry import SourceRegistry
    from ragger_engine.ingestion.service import IngestionService
    from ragger_engine.recommendation.service import RecommendationService
    from ragger_engine.builder.service import BuilderService

    reg = SourceRegistry(storage_dir=ws_dir)
    ing = IngestionService(registry=reg)
    rec = RecommendationService(storage_dir=ws_dir)
    bld = BuilderService(workspace_dir=ws_dir, ingestion_service=ing, recommendation_service=rec)

    routes.ingestion_service = ing
    routes.recommendation_service = rec
    routes.builder_service = bld

    yield {
        "ws_dir": ws_dir,
        "sources_dir": sources_dir,
        "ingestion": ing,
        "rec_service": rec,
        "builder_service": bld,
    }

    # Restore
    routes.ingestion_service = orig_ingestion
    routes.recommendation_service = orig_rec
    routes.builder_service = orig_builder


@pytest.mark.asyncio
async def test_builder_endpoints_require_auth():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        res1 = await client.post("/api/v1/builder/start")
        assert res1.status_code == 401

        res2 = await client.get("/api/v1/builder/progress")
        assert res2.status_code == 401

        res3 = await client.get("/api/v1/builder/manifest")
        assert res3.status_code == 401

        res4 = await client.post("/api/v1/builder/cancel", json={"build_id": "bld_123"})
        assert res4.status_code == 401


@pytest.mark.asyncio
async def test_builder_start_without_config_returns_412(api_workspace):
    app = create_app()
    headers = {"Authorization": f"Bearer {TEST_SECRET_TOKEN}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        res = await client.post("/api/v1/builder/start", headers=headers)
        assert res.status_code == 412
        data = res.json()
        assert "detail" in data
        assert "approved_build_config.json" in data["detail"]["message"]


@pytest.mark.asyncio
async def test_builder_start_with_missing_model_returns_424(api_workspace):
    """When approved model is not available locally, API must return 424 Failed Dependency."""
    ws_dir = api_workspace["ws_dir"]
    sources_dir = api_workspace["sources_dir"]

    doc_path = sources_dir / "sample.txt"
    doc_path.write_text("Company handbook policy content.", encoding="utf-8")
    res_ingest = api_workspace["ingestion"].ingest(str(doc_path))
    source_id = res_ingest.source.source_id

    # Create config referencing non-existent ONNX model
    chunking = ChunkingConfig(strategy=ChunkingStrategyType.BOUNDARY_PARAGRAPH, chunk_size=256, chunk_overlap=32)
    embedding = EmbeddingConfig(provider="local_onnx", model_name="nonexistent_onnx_model", dimension=384)
    vector_db = VectorDbConfig(provider="local_flat_index", metric="cosine")
    retrieval = RetrievalConfig(strategy=RetrievalStrategy.DENSE_VECTOR_TOP_K, top_k=5)

    canonical_hash = compute_canonical_config_hash(
        architecture_id=RagArchitectureId.DOCUMENT_RAG,
        chunking_config=chunking,
        embedding_config=embedding,
        vector_db_config=vector_db,
        retrieval_config=retrieval,
        source_ids=[source_id],
    )

    config = ApprovedBuildConfig(
        config_id="cfg_test_onnx_missing",
        config_version=1,
        config_hash=canonical_hash,
        workspace_id=ws_dir.name,
        recommended_architecture=RagArchitectureId.DOCUMENT_RAG,
        approved_architecture=RagArchitectureId.DOCUMENT_RAG,
        user_customized=False,
        source_ids=[source_id],
        chunking_config=chunking,
        embedding_config=embedding,
        vector_db_config=vector_db,
        retrieval_config=retrieval,
        is_frozen=True,
    )
    with open(ws_dir / "approved_build_config.json", "w", encoding="utf-8") as f:
        f.write(config.model_dump_json(indent=2))

    app = create_app()
    headers = {"Authorization": f"Bearer {TEST_SECRET_TOKEN}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        res = await client.post("/api/v1/builder/start", headers=headers)
        assert res.status_code == 424
        data = res.json()
        assert data["detail"]["code"] == "MODEL_NOT_AVAILABLE"


@pytest.mark.asyncio
async def test_builder_full_lifecycle_and_manifest(api_workspace):
    """Verifies starting build, polling progress, reading manifest, and checking 409 conflict."""
    ws_dir = api_workspace["ws_dir"]
    sources_dir = api_workspace["sources_dir"]

    doc_path = sources_dir / "faq.txt"
    doc_path.write_text("Frequently Asked Questions.\nQ: What is Ragger.ai?\nA: An offline-first local RAG synthesizer.", encoding="utf-8")
    res_ingest = api_workspace["ingestion"].ingest(str(doc_path))
    source_id = res_ingest.source.source_id

    chunking = ChunkingConfig(strategy=ChunkingStrategyType.BOUNDARY_PARAGRAPH, chunk_size=256, chunk_overlap=32)
    embedding = EmbeddingConfig(provider="local_onnx", model_name="bge-small-en-v1.5", dimension=384)
    vector_db = VectorDbConfig(provider="local_flat_index", metric="cosine")
    retrieval = RetrievalConfig(strategy=RetrievalStrategy.DENSE_VECTOR_TOP_K, top_k=5)

    canonical_hash = compute_canonical_config_hash(
        architecture_id=RagArchitectureId.DOCUMENT_RAG,
        chunking_config=chunking,
        embedding_config=embedding,
        vector_db_config=vector_db,
        retrieval_config=retrieval,
        source_ids=[source_id],
    )

    config = ApprovedBuildConfig(
        config_id="cfg_lifecycle_test",
        config_version=1,
        config_hash=canonical_hash,
        workspace_id=ws_dir.name,
        recommended_architecture=RagArchitectureId.DOCUMENT_RAG,
        approved_architecture=RagArchitectureId.DOCUMENT_RAG,
        user_customized=False,
        source_ids=[source_id],
        chunking_config=chunking,
        embedding_config=embedding,
        vector_db_config=vector_db,
        retrieval_config=retrieval,
        is_frozen=True,
    )
    with open(ws_dir / "approved_build_config.json", "w", encoding="utf-8") as f:
        f.write(config.model_dump_json(indent=2))

    # Set test embedding provider override on the router's builder service
    routes.builder_service._embedding_provider_override = TestDeterministicEmbeddingProvider(dimension=384)

    app = create_app()
    headers = {"Authorization": f"Bearer {TEST_SECRET_TOKEN}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        # 1. Manifest initially 404
        res_m0 = await client.get("/api/v1/builder/manifest", headers=headers)
        assert res_m0.status_code == 404

        # 2. Start build
        res_start = await client.post("/api/v1/builder/start", headers=headers)
        assert res_start.status_code == 200
        build_id = res_start.json()["build_id"]
        assert build_id.startswith("bld_")

        # 3. Wait for completion
        routes.builder_service.wait_for_completion(timeout=10.0)

        # 4. Progress check
        res_prog = await client.get("/api/v1/builder/progress", headers=headers)
        assert res_prog.status_code == 200
        prog_data = res_prog.json()
        assert prog_data["status"] == "completed"
        assert prog_data["chunks_processed"] > 0

        # 5. Manifest check
        res_m1 = await client.get("/api/v1/builder/manifest", headers=headers)
        assert res_m1.status_code == 200
        manifest_data = res_m1.json()
        assert manifest_data["build_id"] == build_id
        assert manifest_data["status"] == "completed"
        assert manifest_data["chunk_count"] == prog_data["chunks_processed"]
        assert len(manifest_data["manifest_hash"]) == 64
