"""
Concurrency and Hot Reload tests for Phase 6 RAG Retrieval Engine.
Verifies thread-safe single-flight cache reloading and seamless index switching.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import pytest

from ragger_engine.builder.models import BuildManifest, Chunk, ChunkMetadata, ChunkType
from ragger_engine.builder.storage.local_flat_store import LocalFlatVectorStore
from ragger_engine.retrieval.models import RetrievalQuery
from ragger_engine.retrieval.service import RetrievalService


@pytest.fixture(autouse=True)
def allow_test_embeddings(monkeypatch):
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EMBEDDINGS", "1")


def create_build(
    workspace_dir: Path,
    build_id: str,
    text_content: str,
    dimension: int = 384,
) -> BuildManifest:
    """Helper to create a standalone build in workspace."""
    build_dir = workspace_dir / "builds" / build_id
    index_dir = build_dir / "index"
    index_dir.mkdir(parents=True, exist_ok=True)

    chunk = Chunk(
        chunk_id=f"chk_{build_id}",
        source_id="src_1",
        text=text_content,
        chunk_type=ChunkType.STANDARD_PARAGRAPH,
        metadata=ChunkMetadata(
            source_id="src_1",
            source_name=f"{build_id}.txt",
            chunk_index=0,
            token_count=10,
        ),
        token_count=10,
    )

    vec = [0.1] * dimension
    store = LocalFlatVectorStore()
    store.add_chunks([chunk], [vec])
    store.persist(index_dir)

    now = datetime.now(timezone.utc)
    manifest_dict = {
        "manifest_id": f"man_{build_id}",
        "workspace_id": "default",
        "build_id": build_id,
        "config_id": f"cfg_{build_id}",
        "config_version": 1,
        "config_hash": "c" * 64,
        "source_ids": ["src_1"],
        "source_hashes": {"src_1": "s" * 64},
        "approved_architecture": "document_rag",
        "chunking_config": {"strategy": "boundary_paragraph", "chunk_size": 512, "chunk_overlap": 64},
        "embedding_config": {"provider": "test_deterministic", "model_name": "bge-small-en-v1.5", "dimension": dimension},
        "vector_db_config": {"provider": "local_flat_index", "metric": "cosine", "index_type": "auto"},
        "retrieval_config": {"strategy": "dense_vector_top_k", "top_k": 5, "rerank_enabled": False},
        "chunk_count": 1,
        "vector_count": 1,
        "embedding_dimension": dimension,
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

    return manifest


import time


def activate_build(workspace_dir: Path, manifest: BuildManifest):
    """Atomically points active_build.json to the specified manifest."""
    pointer = {
        "active_build_id": manifest.build_id,
        "manifest_id": manifest.manifest_id,
        "manifest_hash": manifest.manifest_hash,
        "activated_at": datetime.now(timezone.utc).isoformat(),
    }
    tmp_path = workspace_dir / f"active_build_{manifest.build_id}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(pointer, f, indent=2)
    target = workspace_dir / "active_build.json"
    for _ in range(50):
        try:
            tmp_path.replace(target)
            return
        except PermissionError:
            time.sleep(0.01)
    tmp_path.replace(target)


def test_retrieval_hot_reload_on_pointer_change(tmp_path):
    """Verifies that switching active_build.json seamlessly reloads the index cache."""
    service = RetrievalService(workspace_dir=tmp_path)

    # 1. Build & activate Build A
    manifest_a = create_build(tmp_path, "bld_A", "Content from version A of document.")
    activate_build(tmp_path, manifest_a)

    res_a = service.retrieve(RetrievalQuery(query="content"))
    assert len(res_a.results) == 1
    assert res_a.results[0].chunk_id == "chk_bld_A"
    assert "version A" in res_a.results[0].text

    # 2. Build & activate Build B
    manifest_b = create_build(tmp_path, "bld_B", "Content from updated version B.")
    activate_build(tmp_path, manifest_b)

    # Query automatically detects pointer change and updates cache
    res_b = service.retrieve(RetrievalQuery(query="content"))
    assert len(res_b.results) == 1
    assert res_b.results[0].chunk_id == "chk_bld_B"
    assert "version B" in res_b.results[0].text


def test_concurrent_retrieval_queries_during_reload(tmp_path):
    """
    Tests high-concurrency query load across multiple threads during build promotion.
    Asserts zero query failures, thread safety, and eventual consistency.
    """
    manifest_initial = create_build(tmp_path, "bld_init", "Initial baseline knowledge chunk.")
    activate_build(tmp_path, manifest_initial)

    service = RetrievalService(workspace_dir=tmp_path)

    # Pre-warm cache
    initial_res = service.retrieve(RetrievalQuery(query="baseline"))
    assert len(initial_res.results) == 1

    manifest_new = create_build(tmp_path, "bld_next", "Updated knowledge chunk.")

    errors = []
    results = []

    def run_query(idx: int):
        try:
            # Halfway through, trigger the pointer update
            if idx == 10:
                activate_build(tmp_path, manifest_new)

            r = service.retrieve(RetrievalQuery(query="knowledge"))
            return r.results[0].chunk_id
        except Exception as e:
            errors.append(str(e))
            return None

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(run_query, i) for i in range(25)]
        for fut in as_completed(futures):
            res_id = fut.result()
            if res_id:
                results.append(res_id)

    # Assert 100% queries succeeded with zero exceptions
    assert len(errors) == 0
    assert len(results) == 25
    # Both old and new chunks were observed safely across threads
    assert "chk_bld_init" in results
    assert "chk_bld_next" in results
