"""
FastAPI HTTP endpoint tests for Grounded Chat generation, SSE streaming, cancellation, and session management.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from ragger_engine.main import app
from ragger_engine.builder.models import BuildManifest, Chunk, ChunkMetadata, ChunkType
from ragger_engine.builder.storage.local_flat_store import LocalFlatVectorStore
from ragger_engine.generation.providers.testing import TestDeterministicLLMProvider


def setup_api_workspace(workspace_dir: Path):
    """Sets up an active build and initializes services."""
    build_id = "bld_api_test"
    build_dir = workspace_dir / "builds" / build_id
    index_dir = build_dir / "index"
    index_dir.mkdir(parents=True, exist_ok=True)

    chunks = [
        Chunk(
            chunk_id="chk_api_01",
            source_id="src_api_doc",
            text="Company core values include integrity, precision, and privacy.",
            chunk_type=ChunkType.STANDARD_PARAGRAPH,
            metadata=ChunkMetadata(
                source_id="src_api_doc",
                source_name="values.pdf",
                chunk_index=0,
                token_count=10,
                page_number=1,
            ),
            token_count=10,
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
        "source_ids": ["src_api_doc"],
        "source_hashes": {"src_api_doc": "b" * 64},
        "approved_architecture": "document_rag",
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

    from ragger_engine.api import routes
    routes.retrieval_service.workspace_dir = workspace_dir
    routes.retrieval_service._active_cache = None

    routes.generation_service.workspace_dir = workspace_dir
    routes.generation_service.sessions_dir = workspace_dir / "chat_sessions"
    routes.generation_service.sessions_dir.mkdir(parents=True, exist_ok=True)
    routes.generation_service._provider_override = TestDeterministicLLMProvider()


def test_chat_generate_endpoint_success(clean_workspace, monkeypatch, auth_headers):
    """Tests POST /api/v1/chat/generate returns 200 with structured citations."""
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EMBEDDINGS", "1")
    monkeypatch.setenv("RAGGER_ALLOW_TEST_LLM", "1")
    setup_api_workspace(clean_workspace)

    client = TestClient(app)
    resp = client.post(
        "/api/v1/chat/generate?workspace_id=default",
        json={"query": "What are the core values?"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "[chk_" not in data["answer"]
    assert "Company core values" in data["answer"]
    assert len(data["valid_citations"]) == 1
    assert data["valid_citations"][0]["chunk_id"] == "chk_api_01"
    assert data["has_insufficient_evidence"] is False


def test_chat_stream_endpoint_sse_events(clean_workspace, monkeypatch, auth_headers):
    """Tests POST /api/v1/chat/stream yields SSE sequence: status -> token -> done."""
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EMBEDDINGS", "1")
    monkeypatch.setenv("RAGGER_ALLOW_TEST_LLM", "1")
    setup_api_workspace(clean_workspace)

    client = TestClient(app)
    resp = client.post(
        "/api/v1/chat/stream?workspace_id=default",
        json={"query": "core values"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    events = []
    current_event = None

    for line in resp.text.split("\n"):
        line = line.strip()
        if line.startswith("event:"):
            current_event = line.replace("event:", "").strip()
        elif line.startswith("data:"):
            data_str = line.replace("data:", "").strip()
            events.append((current_event, json.loads(data_str)))

    event_names = [ev[0] for ev in events]
    assert "status" in event_names
    assert "token" in event_names
    assert "done" in event_names

    # Check terminal done event payload
    done_event = next(ev[1] for ev in events if ev[0] == "done")
    assert done_event["state"] == "completed"
    assert done_event["valid_citations"][0]["chunk_id"] == "chk_api_01"


def test_chat_session_lifecycle_and_deletion(clean_workspace, monkeypatch, auth_headers):
    """Tests session listing, retrieval by ID, and deletion endpoints."""
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EMBEDDINGS", "1")
    monkeypatch.setenv("RAGGER_ALLOW_TEST_LLM", "1")
    setup_api_workspace(clean_workspace)

    client = TestClient(app)

    # 1. Create message
    gen_resp = client.post(
        "/api/v1/chat/generate?workspace_id=default",
        json={"query": "core values"},
        headers=auth_headers,
    )
    session_id = gen_resp.json()["session_id"]

    # 2. List sessions
    list_resp = client.get("/api/v1/chat/sessions?workspace_id=default", headers=auth_headers)
    assert list_resp.status_code == 200
    sessions = list_resp.json()
    assert any(s["session_id"] == session_id for s in sessions)

    # 3. Get session by ID
    get_resp = client.get(f"/api/v1/chat/sessions/{session_id}?workspace_id=default", headers=auth_headers)
    assert get_resp.status_code == 200
    sess_data = get_resp.json()
    assert len(sess_data["messages"]) == 2

    # 4. Delete session
    del_resp = client.delete(f"/api/v1/chat/sessions/{session_id}?workspace_id=default", headers=auth_headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True

    # 5. Subsequent get returns 404
    get_resp404 = client.get(f"/api/v1/chat/sessions/{session_id}?workspace_id=default", headers=auth_headers)
    assert get_resp404.status_code == 404


def test_chat_config_endpoints(clean_workspace, monkeypatch, auth_headers):
    """Tests GET and POST /api/v1/chat/config."""
    setup_api_workspace(clean_workspace)
    client = TestClient(app)

    # Get default config
    get_resp = client.get("/api/v1/chat/config", headers=auth_headers)
    assert get_resp.status_code == 200
    cfg = get_resp.json()
    assert cfg["provider"] in ("ollama", "test_deterministic", "local_gguf")

    # Update config
    update_resp = client.post(
        "/api/v1/chat/config",
        json={"provider": "ollama", "model_name": "mistral:7b", "temperature": 0.2, "max_tokens": 512},
        headers=auth_headers,
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["model_name"] == "mistral:7b"
    assert updated["temperature"] == 0.2
