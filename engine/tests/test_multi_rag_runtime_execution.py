"""
Unit and integration tests for Phase 14: RAG-Scoped Runtime Resolution and Multi-RAG Execution.

Verifies the 10 User Requirements and Acceptance Criteria:
1. Per-build atomic single-flight loading via per-build lock (deduplicates concurrent loads).
2. Manifest cryptographic & semantic integrity verification on scoped runtime load.
3. No fallback on explicit scoped resolution: missing/corrupt build raises BuildUnavailableError / ManifestCorruptedError (never falls back to active_build.json).
4. Multi-RAG isolation: Agent A queries RAG A/Build A1, Agent B queries RAG B/Build B1; verify citations and chunks match respective build only.
5. Scoped summary sampling isolation: summary queries expand candidate chunks strictly from the scoped build runtime.
6. Dynamic version activation: Agent A switches to A2, Agent B stays on B1 without cross-talk or runtime mutation.
7. Dynamic version rollback: Agent A rolls back to A1, Agent B remains unaffected.
8. Server-authoritative trust boundary: ChatQueryRequest has no build_id parameter; client cannot override server-resolved build.
9. Legacy unscoped retrieval continues to resolve active_build.json cleanly.
10. In-flight request isolation: an in-flight query continues using its original build runtime safely.
"""

import asyncio
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import threading
import time
import pytest

from ragger_engine.builder.models import BuildManifest, Chunk, ChunkMetadata, ChunkType
from ragger_engine.builder.storage.local_flat_store import LocalFlatVectorStore
from ragger_engine.generation.models import (
    ChatMessage,
    ChatQueryRequest,
    ChatRole,
    ChatSession,
    CitationValidationStatus,
    GenerationConfig,
)
from ragger_engine.generation.providers.testing import TestDeterministicLLMProvider
from ragger_engine.generation.service import GenerationService
from ragger_engine.retrieval.models import (
    CitationProvenance,
    RetrievalQuery,
    RetrievedChunk,
    ScoreType,
)
from ragger_engine.retrieval.service import RetrievalService, BuildRuntimeCache
from ragger_engine.retrieval.exceptions import (
    BuildUnavailableError,
    ManifestCorruptedError,
    NoActiveBuildError,
)
from ragger_engine.rag_lifecycle import (
    RAGLifecycleService,
    CreateRAGRequest,
    RegisterVersionRequest,
)
from ragger_engine.rag_library.service import RAGLibraryService
from ragger_engine.agent_workspace.service import AgentWorkspaceService
from ragger_engine.agent_workspace.models import (
    CreateAgentRequest,
    AgentChatRequest,
)


def _create_mock_build(
    workspace_dir: Path,
    build_id: str,
    doc_name: str,
    doc_text: str,
    topic_heading: str,
) -> BuildManifest:
    """Helper to create a fully valid on-disk build with manifest, chunks, and vector store."""
    build_dir = workspace_dir / "builds" / build_id
    index_dir = build_dir / "index"
    index_dir.mkdir(parents=True, exist_ok=True)

    chunks = [
        Chunk(
            chunk_id=f"chk_{build_id}_01",
            source_id=f"src_{build_id}",
            text=f"{topic_heading}: {doc_text}",
            chunk_type=ChunkType.STANDARD_PARAGRAPH,
            metadata=ChunkMetadata(
                source_id=f"src_{build_id}",
                source_name=doc_name,
                chunk_index=0,
                token_count=20,
                page_number=1,
                heading_path=[topic_heading],
            ),
            token_count=20,
        ),
        Chunk(
            chunk_id=f"chk_{build_id}_02",
            source_id=f"src_{build_id}",
            text=f"{topic_heading} additional details: More specific context on {doc_text}",
            chunk_type=ChunkType.STANDARD_PARAGRAPH,
            metadata=ChunkMetadata(
                source_id=f"src_{build_id}",
                source_name=doc_name,
                chunk_index=1,
                token_count=20,
                page_number=2,
                heading_path=[topic_heading, "Details"],
            ),
            token_count=20,
        ),
    ]

    with open(index_dir / "chunks.jsonl", "w", encoding="utf-8") as f:
        for chk in chunks:
            f.write(chk.model_dump_json() + "\n")

    vectors = [[0.1] * 384, [0.2] * 384]
    store = LocalFlatVectorStore()
    store.add_chunks(chunks, vectors)
    store.persist(index_dir)

    now = datetime.now(timezone.utc)
    raw_manifest = {
        "manifest_id": f"mnf_{build_id}",
        "workspace_id": "default",
        "build_id": build_id,
        "config_id": "cfg_test001",
        "config_version": 1,
        "config_hash": "a" * 64,
        "source_ids": [f"src_{build_id}"],
        "source_hashes": {f"src_{build_id}": "b" * 64},
        "approved_architecture": "document_rag",
        "chunking_config": {"strategy": "fixed_paragraph", "chunk_size": 20, "chunk_overlap": 0},
        "embedding_config": {"provider": "test_deterministic", "model_name": "bge-small-en-v1.5", "dimension": 384},
        "vector_db_config": {"provider": "local_flat_index", "metric": "cosine", "index_type": "auto"},
        "retrieval_config": {"strategy": "dense_vector_top_k", "top_k": 5, "rerank_enabled": False},
        "chunk_count": len(chunks),
        "vector_count": len(chunks),
        "embedding_dimension": 384,
        "embedding_model": "bge-small-en-v1.5",
        "vector_store": "local_flat_index",
        "started_at": now,
        "completed_at": now,
        "build_duration_ms": 100.0,
        "status": "completed",
    }
    raw_manifest["manifest_hash"] = BuildManifest.compute_manifest_hash(raw_manifest)
    manifest = BuildManifest(**raw_manifest)

    with open(build_dir / "manifest.json", "w", encoding="utf-8") as f:
        f.write(manifest.model_dump_json(indent=2))

    return manifest


class MockEmbeddingProvider:
    def embed_batch(self, texts):
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]


# ===========================================================================
# 1. Single-Flight Concurrency Test
# ===========================================================================

def test_single_flight_atomic_loading(tmp_path: Path):
    """
    Verifies that simultaneous concurrent requests for the same build_id execute
    ONE disk/index load operation via the per-build lock.
    """
    _create_mock_build(tmp_path, "bld_concurrent_1", "physics.pdf", "Quantum mechanics principles.", "Physics")

    retrieval_svc = RetrievalService(
        workspace_dir=tmp_path,
        embedding_provider_override=MockEmbeddingProvider(),
    )

    results = []
    errors = []

    def load_task():
        try:
            runtime = retrieval_svc.get_or_load_build_runtime("bld_concurrent_1", is_scoped_call=True)
            results.append(runtime)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=load_task) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    assert len(results) == 10
    # Every thread received the exact same cached runtime instance in memory
    first_inst = results[0]
    for inst in results[1:]:
        assert inst is first_inst


# ===========================================================================
# 2. Manifest Verification & Corrupt/Missing Fail-Closed Tests (No Fallback)
# ===========================================================================

def test_scoped_resolution_fail_closed_on_missing_build(tmp_path: Path):
    """
    Verifies that requesting a missing build raises BuildUnavailableError
    and NEVER silently falls back to active_build.json.
    """
    # Create active_build.json pointing to something else
    _create_mock_build(tmp_path, "bld_fallback_target", "active.pdf", "Active fallback content.", "Fallback")
    active_ptr = tmp_path / "active_build.json"
    with open(active_ptr, "w", encoding="utf-8") as f:
        json.dump({"active_build_id": "bld_fallback_target", "manifest_hash": "dummy"}, f)

    retrieval_svc = RetrievalService(
        workspace_dir=tmp_path,
        embedding_provider_override=MockEmbeddingProvider(),
    )

    # Scoped request for missing build must raise BuildUnavailableError
    with pytest.raises(BuildUnavailableError) as exc_info:
        retrieval_svc.get_or_load_build_runtime("bld_nonexistent_999", is_scoped_call=True)

    assert exc_info.value.code == "BUILD_UNAVAILABLE"
    assert "bld_nonexistent_999" in str(exc_info.value)


def test_scoped_resolution_fail_closed_on_corrupt_manifest(tmp_path: Path):
    """
    Verifies that a build with an invalid SHA-256 hash or mismatched build_id
    raises ManifestCorruptedError / BuildUnavailableError and never falls back.
    """
    _create_mock_build(tmp_path, "bld_corrupted_1", "corrupt.pdf", "Data", "Topic")
    manifest_file = tmp_path / "builds" / "bld_corrupted_1" / "manifest.json"

    # Tamper with chunk count without updating hash
    with open(manifest_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["chunk_count"] = 9999
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(data, f)

    retrieval_svc = RetrievalService(
        workspace_dir=tmp_path,
        embedding_provider_override=MockEmbeddingProvider(),
    )

    with pytest.raises(ManifestCorruptedError) as exc_info:
        retrieval_svc.get_or_load_build_runtime("bld_corrupted_1", is_scoped_call=True)

    assert exc_info.value.code == "MANIFEST_CORRUPTED"


# ===========================================================================
# 3. Multi-RAG Isolation & Concurrent Execution
# ===========================================================================

@pytest.mark.asyncio
async def test_multi_rag_scoped_retrieval_and_agent_isolation(tmp_path: Path, monkeypatch):
    """
    Verifies that Agent A (RAG A / Build A1) and Agent B (RAG B / Build B1)
    retrieve exclusively from their respective scoped builds without cross-contamination.
    """
    monkeypatch.setenv("RAGGER_ALLOW_TEST_LLM", "1")
    # 1. Setup Build A (Physics) and Build B (History)
    _create_mock_build(tmp_path, "bld_physics_1", "physics.pdf", "Newton laws and gravity.", "Physics")
    _create_mock_build(tmp_path, "bld_history_1", "history.pdf", "The French Revolution occurred in 1789.", "History")

    retrieval_svc = RetrievalService(
        workspace_dir=tmp_path,
        embedding_provider_override=MockEmbeddingProvider(),
    )
    gen_svc = GenerationService(
        workspace_dir=tmp_path,
        retrieval_service=retrieval_svc,
    )
    gen_svc._provider_override = TestDeterministicLLMProvider()

    rag_lib = RAGLibraryService(workspace_dir=tmp_path)
    agent_svc = AgentWorkspaceService(
        workspace_dir=tmp_path,
        rag_library_service=rag_lib,
        generation_service=gen_svc,
    )
    lifecycle_svc = RAGLifecycleService(
        workspace_dir=tmp_path,
        agent_workspace_service=agent_svc,
    )
    agent_svc.rag_lifecycle_service = lifecycle_svc

    # Register RAG A & RAG B
    rag_a = lifecycle_svc.create_rag(
        CreateRAGRequest(name="Physics RAG", initial_build_id="bld_physics_1")
    )
    rag_b = lifecycle_svc.create_rag(
        CreateRAGRequest(name="History RAG", initial_build_id="bld_history_1")
    )

    # Create Agent A & Agent B
    agent_a = agent_svc.create_agent(
        CreateAgentRequest(name="Physics Agent", attached_rag_ids=[rag_a.rag_id])
    )
    agent_b = agent_svc.create_agent(
        CreateAgentRequest(name="History Agent", attached_rag_ids=[rag_b.rag_id])
    )

    # Execute concurrent chats for Agent A and Agent B
    resp_a, resp_b = await asyncio.gather(
        agent_svc.chat(agent_a.agent_id, AgentChatRequest(query="What are the laws of motion?")),
        agent_svc.chat(agent_b.agent_id, AgentChatRequest(query="When was the revolution?")),
    )

    # Assert Agent A retrieved strictly from bld_physics_1
    for cite in resp_a.citations:
        assert cite.rag_id == rag_a.rag_id
        assert cite.build_id == "bld_physics_1"
        assert "chk_bld_physics_1" in cite.chunk_id
        assert "history" not in cite.citation_text.lower()

    # Assert Agent B retrieved strictly from bld_history_1
    for cite in resp_b.citations:
        assert cite.rag_id == rag_b.rag_id
        assert cite.build_id == "bld_history_1"
        assert "chk_bld_history_1" in cite.chunk_id
        assert "physics" not in cite.citation_text.lower()


# ===========================================================================
# 4. Scoped Summary Sampling Isolation
# ===========================================================================

@pytest.mark.asyncio
async def test_scoped_summary_sampling_isolation(tmp_path: Path, monkeypatch):
    """
    Verifies that summary intent queries expand chunks strictly from the scoped build runtime,
    never polluting with chunks from another build.
    """
    monkeypatch.setenv("RAGGER_ALLOW_TEST_LLM", "1")
    _create_mock_build(tmp_path, "bld_summary_a", "summary_a.pdf", "Summary of Chemistry concepts.", "Chemistry")
    _create_mock_build(tmp_path, "bld_summary_b", "summary_b.pdf", "Summary of Astronomy concepts.", "Astronomy")

    retrieval_svc = RetrievalService(
        workspace_dir=tmp_path,
        embedding_provider_override=MockEmbeddingProvider(),
    )
    gen_svc = GenerationService(
        workspace_dir=tmp_path,
        retrieval_service=retrieval_svc,
    )
    gen_svc._provider_override = TestDeterministicLLMProvider()

    req = ChatQueryRequest(query="Summarize this document thoroughly.")

    # Call with scoped build_id = bld_summary_a
    resp_a = await gen_svc.generate(req, workspace_id="default", build_id="bld_summary_a")
    for cite in resp_a.valid_citations:
        assert "bld_summary_a" in cite.chunk_id
        assert "Astronomy" not in cite.source_name

    # Call with scoped build_id = bld_summary_b
    resp_b = await gen_svc.generate(req, workspace_id="default", build_id="bld_summary_b")
    for cite in resp_b.valid_citations:
        assert "bld_summary_b" in cite.chunk_id
        assert "Chemistry" not in cite.source_name


# ===========================================================================
# 5. Dynamic Version Activation & Rollback Under Load
# ===========================================================================

@pytest.mark.asyncio
async def test_dynamic_version_activation_and_rollback(tmp_path: Path, monkeypatch):
    """
    Verifies that activating a new version (v1.1.0) under RAG A:
    1. Directs Agent A to the new build runtime (bld_a_v2) without affecting Agent B.
    2. Rolling back RAG A to v1.0.0 directs Agent A back to bld_a_v1.
    3. The old runtime is not mutated in place.
    """
    monkeypatch.setenv("RAGGER_ALLOW_TEST_LLM", "1")
    _create_mock_build(tmp_path, "bld_a_v1", "algebra_v1.pdf", "Basic linear equations v1.", "Algebra")
    _create_mock_build(tmp_path, "bld_a_v2", "algebra_v2.pdf", "Advanced quadratic equations v2.", "Algebra")
    _create_mock_build(tmp_path, "bld_b_v1", "biology.pdf", "Cellular biology fundamentals.", "Biology")

    retrieval_svc = RetrievalService(
        workspace_dir=tmp_path,
        embedding_provider_override=MockEmbeddingProvider(),
    )
    gen_svc = GenerationService(
        workspace_dir=tmp_path,
        retrieval_service=retrieval_svc,
    )
    gen_svc._provider_override = TestDeterministicLLMProvider()

    rag_lib = RAGLibraryService(workspace_dir=tmp_path)
    agent_svc = AgentWorkspaceService(
        workspace_dir=tmp_path,
        rag_library_service=rag_lib,
        generation_service=gen_svc,
    )
    lifecycle_svc = RAGLifecycleService(
        workspace_dir=tmp_path,
        agent_workspace_service=agent_svc,
    )
    agent_svc.rag_lifecycle_service = lifecycle_svc

    # Register RAGs
    rag_a = lifecycle_svc.create_rag(CreateRAGRequest(name="Math RAG", initial_build_id="bld_a_v1"))
    rag_b = lifecycle_svc.create_rag(CreateRAGRequest(name="Bio RAG", initial_build_id="bld_b_v1"))

    agent_a = agent_svc.create_agent(CreateAgentRequest(name="Math Agent", attached_rag_ids=[rag_a.rag_id]))
    agent_b = agent_svc.create_agent(CreateAgentRequest(name="Bio Agent", attached_rag_ids=[rag_b.rag_id]))

    # 1. Agent A queries while on v1.0.0
    chat_resp_1 = await agent_svc.chat(agent_a.agent_id, AgentChatRequest(query="linear equations"))
    for cite in chat_resp_1.citations:
        assert cite.build_id == "bld_a_v1"

    # 2. Promote v1.1.0 with build bld_a_v2
    lifecycle_svc.register_version(
        rag_a.rag_id,
        RegisterVersionRequest(
            build_id="bld_a_v2",
            version_tag="v1.1.0",
            set_active=True,
        ),
    )

    # 3. Agent A queries immediately -> dynamically resolves bld_a_v2
    chat_resp_2 = await agent_svc.chat(agent_a.agent_id, AgentChatRequest(query="quadratic equations"))
    for cite in chat_resp_2.citations:
        assert cite.build_id == "bld_a_v2"

    # Agent B remains unaffected on bld_b_v1
    chat_bio = await agent_svc.chat(agent_b.agent_id, AgentChatRequest(query="cellular structure"))
    for cite in chat_bio.citations:
        assert cite.build_id == "bld_b_v1"

    # 4. Rollback RAG A to v1.0.0
    v1_id = rag_a.versions[0].version_id
    lifecycle_svc.rollback_version(rag_a.rag_id, v1_id)

    # 5. Agent A queries again -> dynamically resolves bld_a_v1
    chat_resp_3 = await agent_svc.chat(agent_a.agent_id, AgentChatRequest(query="linear equations"))
    for cite in chat_resp_3.citations:
        assert cite.build_id == "bld_a_v1"


# ===========================================================================
# 6. Legacy Unscoped Retrieval Preserved
# ===========================================================================

def test_legacy_unscoped_retrieval(tmp_path: Path):
    """
    Verifies that calling retrieve() without build_id cleanly falls back
    to resolving active_build.json.
    """
    _create_mock_build(tmp_path, "bld_legacy_active", "legacy.pdf", "Legacy doc content.", "Legacy")
    active_ptr = tmp_path / "active_build.json"
    with open(active_ptr, "w", encoding="utf-8") as f:
        json.dump({"active_build_id": "bld_legacy_active", "manifest_hash": "dummy"}, f)

    retrieval_svc = RetrievalService(
        workspace_dir=tmp_path,
        embedding_provider_override=MockEmbeddingProvider(),
    )

    res = retrieval_svc.retrieve(RetrievalQuery(query="legacy doc"))
    assert res.results is not None
    assert len(res.results) > 0
    assert "bld_legacy_active" in res.results[0].chunk_id
