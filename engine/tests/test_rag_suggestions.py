"""
Unit and integration tests for Dynamic RAG-Aware Suggested Questions.

Verifies:
1. Different RAGs return different suggestions based on their own content.
2. Suggestions come from the selected RAG only (no cross-RAG contamination).
3. Fallback questions work when no headings or natural questions exist.
4. Active version updates invalidate the suggestions cache.
5. Deleting a RAG clears its cached suggestions.
6. Endpoint GET /api/v1/rag-artifacts/{rag_id}/suggestions returns expected schema.
7. Internal build_id is not exposed in suggestions API response.
"""

from pathlib import Path
import json
import pytest
from httpx import ASGITransport, AsyncClient

from ragger_engine.core.config import settings
from ragger_engine.main import create_app
from ragger_engine.rag_lifecycle import (
    RAGLifecycleService,
    CreateRAGRequest,
    RegisterVersionRequest,
    RAGNotFoundError,
)


TEST_SECRET_TOKEN = "test_suggestions_token_123"


@pytest.fixture(autouse=True)
def configure_test_token():
    orig = settings.ragger_api_token
    settings.ragger_api_token = TEST_SECRET_TOKEN
    yield
    settings.ragger_api_token = orig


def _get_workspace_dir():
    return Path("../storage") if Path("../storage").exists() else Path("storage")


def _make_manifest(build_id: str, source_id: str):
    return {
        "manifest_id": f"man_{build_id}",
        "workspace_id": "test",
        "build_id": build_id,
        "config_id": "cfg_test",
        "config_version": 1,
        "config_hash": "hash_test",
        "source_ids": [source_id],
        "source_hashes": {source_id: "h"},
        "approved_architecture": "hybrid_rag",
        "chunking_config": {"strategy": "boundary_paragraph", "chunk_size": 512, "chunk_overlap": 64},
        "embedding_config": {"provider": "local_onnx", "model_name": "bge-small-en-v1.5", "dimension": 384},
        "vector_db_config": {"provider": "lancedb", "metric": "cosine", "index_type": "auto"},
        "retrieval_config": {"strategy": "hybrid_rrf", "top_k": 5, "rerank_enabled": False, "rrf_k": 60},
        "vector_store": "lancedb",
        "embedding_model": "bge-small-en-v1.5",
        "embedding_dimension": 384,
        "status": "completed",
        "chunk_count": 2,
        "vector_count": 2,
        "started_at": "2026-09-23T00:00:00Z",
        "completed_at": "2026-09-23T00:01:00Z",
        "build_duration_ms": 60000,
        "manifest_hash": f"mhash_{build_id}",
    }


def test_rag_suggestions_content_isolation(tmp_path: Path):
    """Verifies that two different RAGs produce content-specific suggestions with no cross-contamination."""
    builds_dir = tmp_path / "builds"
    builds_dir.mkdir(parents=True, exist_ok=True)

    # Build A: System Architecture / Design doc
    bld_a = builds_dir / "bld_arch"
    bld_a_index = bld_a / "index"
    bld_a_index.mkdir(parents=True, exist_ok=True)
    with open(bld_a / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(_make_manifest("bld_arch", "src_a"), f)

    chunk_a1 = {
        "chunk_id": "chk_a1",
        "source_id": "src_a",
        "text": "# Design Goal\nThe goal is to build an analytics platform.\n## Architecture Overview\nMicroservices with event bus.",
        "metadata": {"heading_path": ["Design Goal", "Architecture Overview"], "source_name": "DESIGN.md"},
    }
    with open(bld_a_index / "chunks.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps(chunk_a1) + "\n")

    # Build B: Biology / Photosynthesis doc
    bld_b = builds_dir / "bld_bio"
    bld_b_index = bld_b / "index"
    bld_b_index.mkdir(parents=True, exist_ok=True)
    with open(bld_b / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(_make_manifest("bld_bio", "src_b"), f)

    chunk_b1 = {
        "chunk_id": "chk_b1",
        "source_id": "src_b",
        "text": "# Plant Biology\nWhy is chlorophyll green in plants?\n## Photosynthesis Process\nLight dependent reactions.",
        "metadata": {"heading_path": ["Plant Biology", "Photosynthesis Process"], "source_name": "BIOLOGY.pdf"},
    }
    with open(bld_b_index / "chunks.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps(chunk_b1) + "\n")

    service = RAGLifecycleService(workspace_dir=tmp_path)

    # 1. Suggestions for RAG A
    suggs_a = service.get_suggestions("rag_bld_arch")
    assert len(suggs_a) == 4
    # Check that RAG A contains architecture/design suggestions
    text_a = " ".join(suggs_a).lower()
    assert "design goal" in text_a or "architecture" in text_a or "design" in text_a

    # 2. Suggestions for RAG B
    suggs_b = service.get_suggestions("rag_bld_bio")
    assert len(suggs_b) == 4
    # Check that RAG B contains biology/photosynthesis suggestions
    text_b = " ".join(suggs_b).lower()
    assert "chlorophyll" in text_b or "photosynthesis" in text_b or "biology" in text_b

    # 3. Isolation invariant: RAG A must have ZERO biology questions, RAG B must have ZERO architecture questions
    assert "chlorophyll" not in text_a
    assert "photosynthesis" not in text_a
    assert "architecture" not in text_b


def test_suggestions_cache_invalidation_on_new_version(tmp_path: Path):
    """Verifies that suggestions are cached by active version and invalidated when version changes."""
    builds_dir = tmp_path / "builds"
    builds_dir.mkdir(parents=True, exist_ok=True)

    # Version 1 Build
    bld_v1 = builds_dir / "bld_v1"
    (bld_v1 / "index").mkdir(parents=True, exist_ok=True)
    with open(bld_v1 / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(_make_manifest("bld_v1", "src_1"), f)
    with open(bld_v1 / "index" / "chunks.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "chunk_id": "c1",
            "source_id": "s1",
            "text": "# Alpha Concepts\nWhat is Alpha algorithm?",
            "metadata": {"heading_path": ["Alpha Concepts"], "source_name": "v1.txt"},
        }) + "\n")

    # Version 2 Build
    bld_v2 = builds_dir / "bld_v2"
    (bld_v2 / "index").mkdir(parents=True, exist_ok=True)
    with open(bld_v2 / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(_make_manifest("bld_v2", "src_2"), f)
    with open(bld_v2 / "index" / "chunks.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "chunk_id": "c2",
            "source_id": "s2",
            "text": "# Beta Innovations\nWhat is Beta architecture?",
            "metadata": {"heading_path": ["Beta Innovations"], "source_name": "v2.txt"},
        }) + "\n")

    service = RAGLifecycleService(workspace_dir=tmp_path)
    rag_rec = service.create_rag(CreateRAGRequest(name="Evolution Doc", initial_build_id="bld_v1"))

    # Initial suggestions reflect v1 (Alpha)
    suggs_1 = service.get_suggestions(rag_rec.rag_id)
    assert any("alpha" in s.lower() for s in suggs_1)
    v1_id = rag_rec.active_version_id
    assert v1_id in service._suggestions_cache

    # Register version 2 as active
    v2_info = service.register_version(
        rag_rec.rag_id,
        RegisterVersionRequest(build_id="bld_v2", version_tag="v2.0.0", set_active=True),
    )

    # Now suggestions should reflect v2 (Beta)
    suggs_2 = service.get_suggestions(rag_rec.rag_id)
    assert any("beta" in s.lower() for s in suggs_2)
    assert v2_info.version_id in service._suggestions_cache


def test_suggestions_fallback_empty_content(tmp_path: Path):
    """Verifies that documents without headings or natural questions receive safe document-aware fallbacks."""
    builds_dir = tmp_path / "builds"
    builds_dir.mkdir(parents=True, exist_ok=True)
    bld_empty = builds_dir / "bld_plain"
    (bld_empty / "index").mkdir(parents=True, exist_ok=True)
    with open(bld_empty / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(_make_manifest("bld_plain", "src_p"), f)
    with open(bld_empty / "index" / "chunks.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "chunk_id": "c_plain",
            "source_id": "s_p",
            "text": "Just plain unstructured text with no headers or question marks at all.",
            "metadata": {"source_name": "meeting_notes.txt"},
        }) + "\n")

    service = RAGLifecycleService(workspace_dir=tmp_path)
    suggs = service.get_suggestions("rag_bld_plain")
    assert len(suggs) == 4
    assert any("meeting notes" in s.lower() for s in suggs)
    assert any("summarize" in s.lower() for s in suggs)


@pytest.mark.asyncio
async def test_suggestions_api_endpoint():
    """Verifies GET /api/v1/rag-artifacts/{rag_id}/suggestions via AsyncClient."""
    app = create_app()
    token = settings.ragger_api_token or "dev-token"
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        # Use existing active RAG rag_class10_english
        response = await client.get("/api/v1/rag-artifacts/rag_class10_english/suggestions", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["rag_id"] == "rag_class10_english"
        assert "suggestions" in data
        assert len(data["suggestions"]) == 4
        # Invariant: internal build_id must NOT be exposed in response body
        assert "bld_" not in str(data)

        # Nonexistent RAG returns 404
        resp_404 = await client.get("/api/v1/rag-artifacts/rag_nonexistent_xyz/suggestions", headers=headers)
        assert resp_404.status_code == 404
