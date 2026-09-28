"""
Unit tests for Generation Gate, security boundaries, and model availability.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import urllib.error
import urllib.request
import pytest
from fastapi.testclient import TestClient

from ragger_engine.main import app
from ragger_engine.builder.models import BuildManifest, Chunk, ChunkMetadata, ChunkType
from ragger_engine.builder.storage.local_flat_store import LocalFlatVectorStore
from ragger_engine.generation.exceptions import ModelNotAvailableError, SessionNotFoundError
from ragger_engine.generation.models import ChatQueryRequest, GenerationConfig
from ragger_engine.generation.providers.ollama import OllamaLLMProvider
from ragger_engine.generation.providers.testing import TestDeterministicLLMProvider
from ragger_engine.generation.service import GenerationService
from ragger_engine.retrieval.service import RetrievalService


def create_test_build(workspace_dir: Path, architecture: str = "document_rag") -> BuildManifest:
    """Creates a valid active build in workspace."""
    build_id = "bld_chat_test"
    build_dir = workspace_dir / "builds" / build_id
    index_dir = build_dir / "index"
    index_dir.mkdir(parents=True, exist_ok=True)

    chunks = [
        Chunk(
            chunk_id="chk_policy_01",
            source_id="src_doc_1",
            text="Employee handbook Chapter 4: Working hours are 9:00 AM to 5:00 PM EST.",
            chunk_type=ChunkType.STANDARD_PARAGRAPH,
            metadata=ChunkMetadata(
                source_id="src_doc_1",
                source_name="handbook.pdf",
                chunk_index=0,
                token_count=15,
                page_number=4,
                heading_path=["Employee Handbook", "Chapter 4"],
            ),
            token_count=15,
        )
    ]
    vectors = [[0.1] * 384]

    store = LocalFlatVectorStore()
    store.add_chunks(chunks, vectors)
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
        "embedding_config": {"provider": "test_deterministic", "model_name": "bge-small-en-v1.5", "dimension": 384},
        "vector_db_config": {"provider": "local_flat_index", "metric": "cosine", "index_type": "auto"},
        "retrieval_config": {"strategy": "dense_vector_top_k", "top_k": 5, "rerank_enabled": False},
        "chunk_count": 1,
        "vector_count": 1,
        "embedding_dimension": 384,
        "embedding_model": "bge-small-en-v1.5",
        "vector_store": "local_flat_index",
        "started_at": now,
        "completed_at": now,
        "build_duration_ms": 100.0,
        "status": "completed",
    }
    manifest_dict["manifest_hash"] = BuildManifest.compute_manifest_hash(manifest_dict)
    manifest = BuildManifest(**manifest_dict)

    with open(build_dir / "manifest.json", "w", encoding="utf-8") as f:
        f.write(manifest.model_dump_json(indent=2))

    pointer = {
        "active_build_id": build_id,
        "manifest_id": manifest.manifest_id,
        "manifest_hash": manifest.manifest_hash,
        "activated_at": now.isoformat(),
    }
    with open(workspace_dir / "active_build.json", "w", encoding="utf-8") as f:
        json.dump(pointer, f, indent=2)

    return manifest


def test_generation_fails_when_no_active_build(clean_workspace):
    """Asserts that generating in a workspace without active build propagates 404 NO_ACTIVE_BUILD."""
    retrieval_svc = RetrievalService(workspace_dir=clean_workspace)
    gen_svc = GenerationService(workspace_dir=clean_workspace, retrieval_service=retrieval_svc)

    with pytest.raises(Exception) as exc_info:
        import asyncio
        asyncio.run(gen_svc.generate(ChatQueryRequest(query="working hours"), workspace_id="default"))
    assert "NO_ACTIVE_BUILD" in str(exc_info.value) or exc_info.type.__name__ == "NoActiveBuildError"


def test_generation_blocks_graph_rag(clean_workspace, monkeypatch):
    """Asserts that Graph RAG returns HTTP 422 ARCHITECTURE_NOT_RETRIEVABLE."""
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EMBEDDINGS", "1")
    monkeypatch.setenv("RAGGER_ALLOW_TEST_LLM", "1")
    create_test_build(clean_workspace, architecture="graph_rag")

    retrieval_svc = RetrievalService(workspace_dir=clean_workspace)
    gen_svc = GenerationService(workspace_dir=clean_workspace, retrieval_service=retrieval_svc)

    with pytest.raises(Exception) as exc_info:
        import asyncio
        asyncio.run(gen_svc.generate(ChatQueryRequest(query="working hours"), workspace_id="default"))
    assert "ARCHITECTURE_NOT_RETRIEVABLE" in str(exc_info.value) or exc_info.type.__name__ == "ArchitectureNotRetrievableError"


def test_generation_missing_model_returns_424_without_pull(monkeypatch):
    """
    Asserts that missing Ollama model returns ModelNotAvailableError (HTTP 424).
    Verifies zero download/pull calls are initiated.
    """
    pull_calls = []

    class MockResponse:
        status = 200

        def read(self):
            # Model 'llama3' is absent
            return json.dumps({"models": [{"name": "mistral:latest"}]}).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    def mock_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "/api/pull" in url:
            pull_calls.append(url)
            raise AssertionError("ILLEGAL: /api/pull was called!")
        return MockResponse()

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    provider = OllamaLLMProvider(model_name="llama3")
    with pytest.raises(ModelNotAvailableError) as exc_info:
        provider.validate_availability()

    assert exc_info.value.code == "MODEL_NOT_AVAILABLE"
    assert "not found in local Ollama instance" in str(exc_info.value)
    # Critical guarantee: zero pull requests
    assert len(pull_calls) == 0


def test_test_double_blocked_without_env_var(monkeypatch):
    """Asserts that TestDeterministicLLMProvider raises ModelNotAvailableError if RAGGER_ALLOW_TEST_LLM != '1'."""
    monkeypatch.delenv("RAGGER_ALLOW_TEST_LLM", raising=False)
    provider = TestDeterministicLLMProvider()
    with pytest.raises(ModelNotAvailableError) as exc_info:
        provider.validate_availability()
    assert exc_info.value.code == "MODEL_NOT_AVAILABLE"
    assert "strictly blocked in production" in str(exc_info.value)


def test_session_ownership_cross_workspace_rejected(clean_workspace):
    """Asserts that attempting to query a session from another workspace returns SessionNotFoundError."""
    retrieval_svc = RetrievalService(workspace_dir=clean_workspace)
    gen_svc = GenerationService(workspace_dir=clean_workspace, retrieval_service=retrieval_svc)

    # Create session belonging to workspace_A
    from ragger_engine.generation.models import ChatSession
    session = ChatSession(
        session_id="sess_ws_a",
        workspace_id="workspace_A",
        title="Test Session",
        messages=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    gen_svc._save_session_atomic(session)

    # Attempt to access using workspace_B
    with pytest.raises(SessionNotFoundError) as exc_info:
        gen_svc.get_session(session_id="sess_ws_a", workspace_id="workspace_B")
    assert exc_info.value.code == "SESSION_NOT_FOUND"


def test_client_cannot_submit_system_role():
    """Asserts that ChatQueryRequest strictly accepts only query, preventing arbitrary system role injection."""
    with pytest.raises(ValueError):
        # extra="forbid" prevents passing role or system instructions
        ChatQueryRequest(query="valid query", role="system")
