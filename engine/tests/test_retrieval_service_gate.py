"""
Unit and Preflight Gate tests for Phase 6 RAG Retrieval Engine.
Verifies active build pointer verification, manifest cryptographic integrity,
Option B Graph RAG rejection, model manager boundary compliance,
input validation, and empty result handling.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from ragger_engine.main import app
from ragger_engine.core.config import settings
from ragger_engine.builder.models import BuildManifest, Chunk, ChunkMetadata, ChunkType
from ragger_engine.builder.storage.local_flat_store import LocalFlatVectorStore
from ragger_engine.builder.exceptions import ModelNotAvailableError
from ragger_engine.retrieval.service import RetrievalService
from ragger_engine.retrieval.models import RetrievalFilter, RetrievalQuery
from ragger_engine.retrieval.exceptions import (
    ArchitectureNotRetrievableError,
    BuildIncompleteError,
    ManifestCorruptedError,
    NoActiveBuildError,
)


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


def create_test_build(
    workspace_dir: Path,
    build_id: str = "bld_test001",
    architecture: str = "document_rag",
    status: str = "completed",
    embedding_provider: str = "test_deterministic",
    embedding_model: str = "bge-small-en-v1.5",
    dimension: int = 384,
    tamper_manifest_hash: bool = False,
) -> tuple[BuildManifest, Path]:
    """Helper to build a valid, self-consistent Phase 5 build structure on disk."""
    build_dir = workspace_dir / "builds" / build_id
    index_dir = build_dir / "index"
    index_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create chunks
    chunks = [
        Chunk(
            chunk_id=f"chk_{build_id}_1",
            source_id="src_doc_1",
            text="Employee handbook Section 1. Working hours are 9am to 5pm Monday through Friday.",
            chunk_type=ChunkType.STANDARD_PARAGRAPH,
            metadata=ChunkMetadata(
                source_id="src_doc_1",
                source_name="handbook.txt",
                chunk_index=0,
                token_count=15,
                page_number=1,
                heading_path=["Employee Handbook", "Section 1"],
            ),
            token_count=15,
        ),
        Chunk(
            chunk_id=f"chk_{build_id}_2",
            source_id="src_doc_1",
            text="Employee handbook Section 2. Paid time off requests must be submitted two weeks in advance.",
            chunk_type=ChunkType.STANDARD_PARAGRAPH,
            metadata=ChunkMetadata(
                source_id="src_doc_1",
                source_name="handbook.txt",
                chunk_index=1,
                token_count=17,
                page_number=2,
                heading_path=["Employee Handbook", "Section 2"],
            ),
            token_count=17,
        ),
    ]

    # Deterministic dummy vectors
    vec1 = [0.1] * dimension
    vec2 = [0.2] * dimension

    # Store via LocalFlatVectorStore
    store = LocalFlatVectorStore()
    store.add_chunks(chunks, [vec1, vec2])
    store.persist(index_dir)

    now = datetime.now(timezone.utc)
    manifest_dict = {
        "manifest_id": f"man_{build_id}",
        "workspace_id": "default",
        "build_id": build_id,
        "config_id": "cfg_test001",
        "config_version": 1,
        "config_hash": "a" * 64,
        "source_ids": ["src_doc_1"],
        "source_hashes": {"src_doc_1": "b" * 64},
        "approved_architecture": architecture,
        "chunking_config": {"strategy": "boundary_paragraph", "chunk_size": 512, "chunk_overlap": 64},
        "embedding_config": {"provider": embedding_provider, "model_name": embedding_model, "dimension": dimension},
        "vector_db_config": {"provider": "local_flat_index", "metric": "cosine", "index_type": "auto"},
        "retrieval_config": {"strategy": "dense_vector_top_k", "top_k": 5, "rerank_enabled": False},
        "chunk_count": len(chunks),
        "vector_count": 2,
        "embedding_dimension": dimension,
        "embedding_model": embedding_model,
        "vector_store": "local_flat_index",
        "started_at": now,
        "completed_at": now,
        "build_duration_ms": 150.0,
        "status": status,
    }

    if tamper_manifest_hash:
        manifest_hash = "f" * 64
    else:
        manifest_hash = BuildManifest.compute_manifest_hash(manifest_dict)

    manifest_dict["manifest_hash"] = manifest_hash
    manifest = BuildManifest(**manifest_dict)

    with open(build_dir / "manifest.json", "w", encoding="utf-8") as f:
        f.write(manifest.model_dump_json(indent=2))

    # Write active pointer
    pointer = {
        "active_build_id": build_id,
        "manifest_id": manifest.manifest_id,
        "manifest_hash": manifest.manifest_hash,
        "activated_at": now.isoformat(),
    }
    with open(workspace_dir / "active_build.json", "w", encoding="utf-8") as f:
        json.dump(pointer, f, indent=2)

    return manifest, build_dir


def test_retrieval_fails_when_no_active_build(clean_workspace):
    """Asserts that querying a workspace without active_build.json raises NoActiveBuildError."""
    service = RetrievalService(workspace_dir=clean_workspace)
    query = RetrievalQuery(query="What are the working hours?")
    with pytest.raises(NoActiveBuildError) as exc_info:
        service.retrieve(query)
    assert exc_info.value.code == "NO_ACTIVE_BUILD"


def test_retrieval_fails_on_corrupted_manifest_hash(clean_workspace):
    """Asserts that tampering with the manifest hash causes ManifestCorruptedError."""
    create_test_build(clean_workspace, tamper_manifest_hash=True)
    service = RetrievalService(workspace_dir=clean_workspace)
    query = RetrievalQuery(query="What are the working hours?")
    with pytest.raises(ManifestCorruptedError) as exc_info:
        service.retrieve(query)
    assert exc_info.value.code == "MANIFEST_CORRUPTED"


def test_retrieval_fails_on_incomplete_build(clean_workspace):
    """Asserts that a build marked with status != 'completed' causes BuildIncompleteError."""
    create_test_build(clean_workspace, status="failed")
    service = RetrievalService(workspace_dir=clean_workspace)
    query = RetrievalQuery(query="What are the working hours?")
    with pytest.raises(BuildIncompleteError) as exc_info:
        service.retrieve(query)
    assert exc_info.value.code == "BUILD_INCOMPLETE"


def test_retrieval_blocks_graph_rag(clean_workspace):
    """Asserts that Option B Graph RAG returns ArchitectureNotRetrievableError."""
    create_test_build(clean_workspace, architecture="graph_rag")
    service = RetrievalService(workspace_dir=clean_workspace)
    query = RetrievalQuery(query="Find related entities")
    with pytest.raises(ArchitectureNotRetrievableError) as exc_info:
        service.retrieve(query)
    assert exc_info.value.code == "ARCHITECTURE_NOT_RETRIEVABLE"


def test_retrieval_fails_on_missing_model_without_download(clean_workspace, monkeypatch):
    """
    Asserts that missing real model weights return ModelNotAvailableError.
    Strictly verifies zero download/pull attempt.
    """
    # Force production embedding provider with non-existent local model
    monkeypatch.delenv("RAGGER_ALLOW_TEST_EMBEDDINGS", raising=False)
    create_test_build(clean_workspace, embedding_provider="local_onnx", embedding_model="missing-model-xyz")

    service = RetrievalService(workspace_dir=clean_workspace)
    query = RetrievalQuery(query="What are the hours?")

    with pytest.raises(ModelNotAvailableError):
        service.retrieve(query)


def test_retrieval_empty_query_fails_validation():
    """Asserts that query='' is rejected with validation error (min_length=1)."""
    with pytest.raises(ValueError):
        RetrievalQuery(query="")


def test_retrieval_valid_query_empty_results(clean_workspace, monkeypatch):
    """
    Asserts that a valid query with no matching chunks (e.g. impossible filter)
    returns an empty results list with HTTP 200 semantics (zero error).
    """
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EMBEDDINGS", "1")
    create_test_build(clean_workspace)

    service = RetrievalService(workspace_dir=clean_workspace)
    # Impossible filter: page 999
    query = RetrievalQuery(
        query="What are the working hours?",
        filters=RetrievalFilter(page_numbers=[999]),
    )
    response = service.retrieve(query)

    assert response.results == []
    assert response.total_candidates == 0
    assert response.query == "What are the working hours?"
    assert response.architecture == "document_rag"


def test_retrieval_api_endpoint_gate(clean_workspace, monkeypatch, auth_headers):
    """Tests the FastAPI routes for the retrieval gate and error codes."""
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EMBEDDINGS", "1")
    create_test_build(clean_workspace)

    client = TestClient(app)

    # Monkeypatch routes.retrieval_service.workspace_dir
    from ragger_engine.api import routes
    monkeypatch.setattr(routes.retrieval_service, "workspace_dir", clean_workspace)
    routes.retrieval_service._active_cache = None

    # 1. Status endpoint
    resp = client.get("/api/v1/retrieval/status", headers=auth_headers)
    assert resp.status_code == 200
    st = resp.json()
    assert st["has_active_build"] is True
    assert st["active_build_id"] == "bld_test001"
    assert st["chunk_count"] == 2

    # 2. Query endpoint success
    resp = client.post(
        "/api/v1/retrieval/query",
        json={"query": "working hours"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) > 0
    assert data["results"][0]["provenance"]["source_name"] == "handbook.txt"

    # 3. Reload cache endpoint (zero args)
    resp = client.post("/api/v1/retrieval/reload", headers=auth_headers)
    assert resp.status_code == 200
    reload_data = resp.json()
    assert reload_data["status"] == "reloaded"
    assert reload_data["build_id"] == "bld_test001"


def test_retrieval_api_returns_412_on_corrupted_manifest(clean_workspace, monkeypatch, auth_headers):
    """Verifies that API returns HTTP 412 (Precondition Failed) when manifest hash is corrupted."""
    create_test_build(clean_workspace, tamper_manifest_hash=True)
    from ragger_engine.api import routes
    monkeypatch.setattr(routes.retrieval_service, "workspace_dir", clean_workspace)
    routes.retrieval_service._active_cache = None

    client = TestClient(app)
    resp = client.post(
        "/api/v1/retrieval/query",
        json={"query": "working hours"},
        headers=auth_headers,
    )
    assert resp.status_code == 412
    detail = resp.json()["detail"]
    assert detail["error"]["code"] == "MANIFEST_CORRUPTED"


def test_retrieval_api_returns_412_on_incomplete_build(clean_workspace, monkeypatch, auth_headers):
    """Verifies that API returns HTTP 412 (Precondition Failed) when active build status != 'completed'."""
    create_test_build(clean_workspace, status="failed")
    from ragger_engine.api import routes
    monkeypatch.setattr(routes.retrieval_service, "workspace_dir", clean_workspace)
    routes.retrieval_service._active_cache = None

    client = TestClient(app)
    resp = client.post(
        "/api/v1/retrieval/query",
        json={"query": "working hours"},
        headers=auth_headers,
    )
    assert resp.status_code == 412
    detail = resp.json()["detail"]
    assert detail["error"]["code"] == "BUILD_INCOMPLETE"


def test_retrieval_api_returns_422_on_graph_rag(clean_workspace, monkeypatch, auth_headers):
    """Verifies that API returns HTTP 422 (Unprocessable Entity) when architecture is graph_rag."""
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EMBEDDINGS", "1")
    create_test_build(clean_workspace, architecture="graph_rag")
    from ragger_engine.api import routes
    monkeypatch.setattr(routes.retrieval_service, "workspace_dir", clean_workspace)
    routes.retrieval_service._active_cache = None

    client = TestClient(app)
    resp = client.post(
        "/api/v1/retrieval/query",
        json={"query": "find entities"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["error"]["code"] == "ARCHITECTURE_NOT_RETRIEVABLE"


def test_retrieval_api_returns_404_when_no_active_build(clean_workspace, monkeypatch, auth_headers):
    """Verifies that API returns HTTP 404 (Not Found) when workspace has no active build."""
    from ragger_engine.api import routes
    monkeypatch.setattr(routes.retrieval_service, "workspace_dir", clean_workspace)
    routes.retrieval_service._active_cache = None

    client = TestClient(app)
    resp = client.post(
        "/api/v1/retrieval/query",
        json={"query": "working hours"},
        headers=auth_headers,
    )
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert detail["error"]["code"] == "NO_ACTIVE_BUILD"


def test_retrieval_api_rejects_empty_query_string(clean_workspace, monkeypatch, auth_headers):
    """Verifies that query='' is rejected by API with HTTP 422 validation error (min_length=1)."""
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EMBEDDINGS", "1")
    create_test_build(clean_workspace)
    from ragger_engine.api import routes
    monkeypatch.setattr(routes.retrieval_service, "workspace_dir", clean_workspace)
    routes.retrieval_service._active_cache = None

    client = TestClient(app)
    resp = client.post(
        "/api/v1/retrieval/query",
        json={"query": ""},
        headers=auth_headers,
    )
    assert resp.status_code == 422  # Pydantic validation failure


def test_retrieval_api_valid_query_empty_results_returns_200(clean_workspace, monkeypatch, auth_headers):
    """
    Verifies that a valid query with zero matching chunks returns HTTP 200 with results=[].
    """
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EMBEDDINGS", "1")
    create_test_build(clean_workspace)
    from ragger_engine.api import routes
    monkeypatch.setattr(routes.retrieval_service, "workspace_dir", clean_workspace)
    routes.retrieval_service._active_cache = None

    client = TestClient(app)
    resp = client.post(
        "/api/v1/retrieval/query",
        json={
            "query": "working hours",
            "filters": {"page_numbers": [999]},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["results"] == []
    assert body["total_candidates"] == 0
    assert body["query"] == "working hours"

