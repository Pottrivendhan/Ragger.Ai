"""
FastAPI HTTP endpoint tests for Phase 8 Evaluation: trigger, progress polling,
cancellation, report retrieval, config management, and auth enforcement.
"""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import pytest
from fastapi.testclient import TestClient

from ragger_engine.main import app
from ragger_engine.builder.models import BuildManifest, Chunk, ChunkMetadata, ChunkType
from ragger_engine.builder.storage.local_flat_store import LocalFlatVectorStore
from ragger_engine.evaluation.providers.test_judge import TestDeterministicEvalJudge
from ragger_engine.generation.providers.testing import TestDeterministicLLMProvider


def setup_eval_api_workspace(workspace_dir: Path):
    """Sets up an active build and initializes routes services for evaluation."""
    build_id = "bld_eval_api"
    build_dir = workspace_dir / "builds" / build_id
    index_dir = build_dir / "index"
    index_dir.mkdir(parents=True, exist_ok=True)

    chunks = [
        Chunk(
            chunk_id="chk_eval_01",
            source_id="src_eval_doc",
            text="Primary data storage is handled by AES-256 encrypted SSD drives with redundancy.",
            chunk_type=ChunkType.STANDARD_PARAGRAPH,
            metadata=ChunkMetadata(
                source_id="src_eval_doc",
                source_name="spec.pdf",
                chunk_index=0,
                token_count=12,
                page_number=1,
            ),
            token_count=12,
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
        "config_id": "cfg_eval_api_01",
        "config_version": 1,
        "config_hash": "a" * 64,
        "source_ids": ["src_eval_doc"],
        "source_hashes": {"src_eval_doc": "b" * 64},
        "approved_architecture": "hybrid_rag",
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

    routes.evaluation_service.workspace_dir = workspace_dir
    routes.evaluation_service.workspace_id = "default"
    routes.evaluation_service.evaluations_dir = workspace_dir / "evaluations"
    routes.evaluation_service.evaluations_dir.mkdir(parents=True, exist_ok=True)
    routes.evaluation_service._judge_override = TestDeterministicEvalJudge()


def test_evaluation_unauthenticated_rejection(clean_workspace):
    """Verifies that missing bearer token receives HTTP 401."""
    client = TestClient(app)
    resp = client.post("/api/v1/evaluation/run?workspace_id=default", json={})
    assert resp.status_code == 401


def test_evaluation_config_endpoints(clean_workspace, auth_headers):
    """Verifies GET and POST /api/v1/evaluation/config."""
    from ragger_engine.api import routes
    routes.evaluation_service.workspace_dir = clean_workspace

    client = TestClient(app)
    # GET default config
    resp = client.get("/api/v1/evaluation/config?workspace_id=default", headers=auth_headers)
    assert resp.status_code == 200
    cfg = resp.json()
    assert cfg["judge_provider"] == "ollama"

    # POST updated config
    cfg["default_sample_size"] = 15
    resp2 = client.post("/api/v1/evaluation/config?workspace_id=default", json=cfg, headers=auth_headers)
    assert resp2.status_code == 200
    assert resp2.json()["default_sample_size"] == 15


@pytest.mark.asyncio
async def test_evaluation_run_and_progress_lifecycle(clean_workspace, monkeypatch, auth_headers):
    import httpx
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EMBEDDINGS", "1")
    monkeypatch.setenv("RAGGER_ALLOW_TEST_LLM", "1")
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EVAL", "1")

    setup_eval_api_workspace(clean_workspace)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Trigger evaluation run
        resp = await client.post(
            "/api/v1/evaluation/run?workspace_id=default",
            json={"sample_size": 3, "sampling_seed": 42},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        eval_id = resp.json()["eval_id"]
        assert eval_id.startswith("eval_")

        # Poll progress until completed
        for _ in range(50):
            prog_resp = await client.get(
                f"/api/v1/evaluation/progress/{eval_id}?workspace_id=default",
                headers=auth_headers,
            )
            assert prog_resp.status_code == 200
            prog = prog_resp.json()
            if prog["state"] in ["completed", "failed", "cancelled"]:
                break
            await asyncio.sleep(0.05)

        assert prog["state"] == "completed"

        # Fetch report
        rep_resp = await client.get(
            f"/api/v1/evaluation/reports/{eval_id}?workspace_id=default",
            headers=auth_headers,
        )
        assert rep_resp.status_code == 200
        report = rep_resp.json()
        assert report["eval_id"] == eval_id
        assert report["quality_score"] >= 0.0

        # List reports
        list_resp = await client.get("/api/v1/evaluation/reports?workspace_id=default", headers=auth_headers)
        assert list_resp.status_code == 200
        assert len(list_resp.json()) >= 1

        # Delete report
        del_resp = await client.delete(
            f"/api/v1/evaluation/reports/{eval_id}?workspace_id=default",
            headers=auth_headers,
        )
        assert del_resp.status_code == 200
        assert del_resp.json()["deleted"] is True
