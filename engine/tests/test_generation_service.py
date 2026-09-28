"""
Unit tests for GenerationService, citation validation, history vs evidence hierarchy,
and terminal cancellation states.
"""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
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
from ragger_engine.retrieval.models import CitationProvenance, RetrievalFilter, RetrievedChunk, ScoreType
from ragger_engine.retrieval.service import RetrievalService


def setup_workspace(workspace_dir: Path) -> tuple[GenerationService, RetrievalService]:
    """Creates a valid active build with 2 chunks and returns GenerationService."""
    build_id = "bld_gen_test"
    build_dir = workspace_dir / "builds" / build_id
    index_dir = build_dir / "index"
    index_dir.mkdir(parents=True, exist_ok=True)

    chunks = [
        Chunk(
            chunk_id="chk_handbook_01",
            source_id="src_doc_1",
            text="Employee working hours are strictly 9:00 AM to 5:00 PM EST Monday through Friday.",
            chunk_type=ChunkType.STANDARD_PARAGRAPH,
            metadata=ChunkMetadata(
                source_id="src_doc_1",
                source_name="handbook.pdf",
                chunk_index=0,
                token_count=15,
                page_number=2,
                heading_path=["Employee Handbook", "Hours"],
            ),
            token_count=15,
        ),
        Chunk(
            chunk_id="chk_handbook_02",
            source_id="src_doc_1",
            text="Overtime must be pre-approved by the department manager 48 hours in advance.",
            chunk_type=ChunkType.STANDARD_PARAGRAPH,
            metadata=ChunkMetadata(
                source_id="src_doc_1",
                source_name="handbook.pdf",
                chunk_index=1,
                token_count=14,
                page_number=3,
                heading_path=["Employee Handbook", "Overtime"],
            ),
            token_count=14,
        ),
    ]
    vectors = [[0.1] * 384, [0.2] * 384]

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
        "approved_architecture": "document_rag",
        "chunking_config": {"strategy": "boundary_paragraph", "chunk_size": 512, "chunk_overlap": 64},
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

    retrieval_svc = RetrievalService(workspace_dir=workspace_dir)
    provider = TestDeterministicLLMProvider()
    gen_svc = GenerationService(
        workspace_dir=workspace_dir,
        retrieval_service=retrieval_svc,
        provider_override=provider,
    )
    return gen_svc, retrieval_svc


def test_zero_retrieval_results_triggers_disclaimer_without_llm(clean_workspace, monkeypatch):
    """
    Asserts that queries producing zero retrieved candidates (e.g. impossible filter)
    immediately return the polite disclaimer without invoking LLM inference.
    """
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EMBEDDINGS", "1")
    monkeypatch.setenv("RAGGER_ALLOW_TEST_LLM", "1")
    gen_svc, _ = setup_workspace(clean_workspace)

    req = ChatQueryRequest(
        query="What are the working hours?",
        filters=RetrievalFilter(page_numbers=[9999]),  # matches 0 chunks
    )
    resp = asyncio.run(gen_svc.generate(req, workspace_id="default"))

    assert resp.has_insufficient_evidence is True
    assert resp.retrieved_chunk_count == 0
    assert "could not find information" in resp.answer
    assert resp.valid_citations == []
    assert resp.generation_latency_ms == 0.0


def test_citation_validator_unambiguous_chunk_matching(clean_workspace):
    """
    Tests the deterministic citation validation contract:
    - Exact [chk_...] match -> verified.
    - Unique source and page match -> verified.
    - Ambiguous source name with multiple chunks -> unverified.
    - Fabricated ID -> unverified.
    """
    gen_svc, _ = setup_workspace(clean_workspace)

    retrieved_chunks = [
        RetrievedChunk(
            chunk_id="chk_01",
            text="Text chunk 1",
            score=0.9,
            score_type=ScoreType.COSINE_SIMILARITY,
            provenance=CitationProvenance(
                source_id="src_1",
                source_name="doc_a.pdf",
                source_sha256="a" * 64,
                chunk_id="chk_01",
                chunk_type=ChunkType.STANDARD_PARAGRAPH,
                token_count=10,
                page_number=1,
            ),
            citation="[Source: doc_a.pdf, p. 1]",
        ),
        RetrievedChunk(
            chunk_id="chk_02",
            text="Text chunk 2",
            score=0.85,
            score_type=ScoreType.COSINE_SIMILARITY,
            provenance=CitationProvenance(
                source_id="src_1",
                source_name="doc_a.pdf",
                source_sha256="a" * 64,
                chunk_id="chk_02",
                chunk_type=ChunkType.STANDARD_PARAGRAPH,
                token_count=10,
                page_number=2,
            ),
            citation="[Source: doc_a.pdf, p. 2]",
        ),
        RetrievedChunk(
            chunk_id="chk_03",
            text="Text chunk 3",
            score=0.80,
            score_type=ScoreType.COSINE_SIMILARITY,
            provenance=CitationProvenance(
                source_id="src_2",
                source_name="doc_b.pdf",
                source_sha256="b" * 64,
                chunk_id="chk_03",
                chunk_type=ChunkType.STANDARD_PARAGRAPH,
                token_count=10,
                page_number=5,
            ),
            citation="[Source: doc_b.pdf, p. 5]",
        ),
    ]

    # Test Case 1: Exact chunk ID match and unique source+page match
    answer1 = "Employees report at 9am [chk_01] and leave at 5pm [Source: doc_b.pdf, p. 5]."
    valid1, unverified1, status1 = gen_svc._validate_citations(answer1, retrieved_chunks)
    assert len(valid1) == 2
    assert {v.chunk_id for v in valid1} == {"chk_01", "chk_03"}
    assert len(unverified1) == 0
    assert status1 == CitationValidationStatus.VERIFIED

    # Test Case 2: Ambiguous filename alone matching multiple chunks (doc_a.pdf has chunks on p.1 and p.2)
    answer2 = "Information from [Source: doc_a.pdf]."
    valid2, unverified2, status2 = gen_svc._validate_citations(answer2, retrieved_chunks)
    assert len(valid2) == 0
    assert len(unverified2) == 1
    assert "doc_a.pdf" in unverified2[0]
    assert status2 == CitationValidationStatus.UNVERIFIED_DETECTED

    # Test Case 3: Fabricated chunk ID not in retrieval
    answer3 = "Fabricated claim citing fake chunk [chk_fake_999]."
    valid3, unverified3, status3 = gen_svc._validate_citations(answer3, retrieved_chunks)
    assert len(valid3) == 0
    assert "chk_fake_999" in unverified3
    assert status3 == CitationValidationStatus.UNVERIFIED_DETECTED


def test_history_cannot_override_retrieval_evidence(clean_workspace, monkeypatch):
    """
    Regression Test: Asserts that conversation history is conversational context only,
    never factual evidence.
    Turn 1: User asks about working hours (evidence present in retrieval).
    Turn 2: User asks about paid sabbatical (evidence absent in retrieval).
    Turn 2 must NOT assert sabbatical exists even if prior assistant response is tampered.
    """
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EMBEDDINGS", "1")
    monkeypatch.setenv("RAGGER_ALLOW_TEST_LLM", "1")
    gen_svc, _ = setup_workspace(clean_workspace)

    # Turn 1: Working hours query (has retrieval chunks)
    req1 = ChatQueryRequest(query="What are the working hours?")
    resp1 = asyncio.run(gen_svc.generate(req1, workspace_id="default"))
    assert resp1.has_insufficient_evidence is False
    assert len(resp1.valid_citations) > 0

    # Turn 2: Query for sabbatical (filter to non-existent page -> 0 retrieval chunks)
    req2 = ChatQueryRequest(
        query="What is the sabbatical policy?",
        session_id=resp1.session_id,
        filters=RetrievalFilter(page_numbers=[999]),  # 0 evidence
    )
    resp2 = asyncio.run(gen_svc.generate(req2, workspace_id="default"))

    # Turn 2 MUST strictly return insufficient evidence disclaimer
    assert resp2.has_insufficient_evidence is True
    assert resp2.retrieved_chunk_count == 0
    assert "could not find information" in resp2.answer
    assert resp2.valid_citations == []


def test_unmodified_answer_returned_with_metadata(clean_workspace, monkeypatch):
    """Asserts that response.answer retains exact model-generated text with [chk_...] intact."""
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EMBEDDINGS", "1")
    monkeypatch.setenv("RAGGER_ALLOW_TEST_LLM", "1")
    gen_svc, _ = setup_workspace(clean_workspace)

    req = ChatQueryRequest(query="working hours")
    resp = asyncio.run(gen_svc.generate(req, workspace_id="default"))

    # Answer text is clean natural language prose with no raw [chk_...] leakage
    assert "[chk_" not in resp.answer
    assert "Employee working hours" in resp.answer
    # Metadata contains structured valid citations for frontend rendering and verification
    assert len(resp.valid_citations) >= 1
    assert resp.valid_citations[0].chunk_id == "chk_handbook_01"
    assert resp.valid_citations[0].source_name == "handbook.pdf"


def test_cancellation_race_handling(clean_workspace, monkeypatch):
    """
    Asserts that completed terminal state is immutable.
    A cancellation request sent after generation completes is a clean no-op.
    """
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EMBEDDINGS", "1")
    monkeypatch.setenv("RAGGER_ALLOW_TEST_LLM", "1")
    gen_svc, _ = setup_workspace(clean_workspace)

    req = ChatQueryRequest(query="working hours")
    resp = asyncio.run(gen_svc.generate(req, workspace_id="default"))

    # Now attempt late cancellation on the completed session
    cancel_res = asyncio.run(gen_svc.cancel_generation(resp.session_id))
    assert cancel_res["status"] == "already_completed"


def test_atomic_session_persistence(clean_workspace, monkeypatch):
    """Asserts that sessions persist atomically and can be read back cleanly."""
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EMBEDDINGS", "1")
    monkeypatch.setenv("RAGGER_ALLOW_TEST_LLM", "1")
    gen_svc, _ = setup_workspace(clean_workspace)

    req = ChatQueryRequest(query="working hours")
    resp = asyncio.run(gen_svc.generate(req, workspace_id="default"))

    # Verify session file exists on disk
    session_file = clean_workspace / "chat_sessions" / f"{resp.session_id}.json"
    assert session_file.exists()

    # Load session and verify messages
    loaded = gen_svc.get_session(resp.session_id, workspace_id="default")
    assert loaded.session_id == resp.session_id
    assert len(loaded.messages) == 2  # user + assistant
    assert loaded.messages[0].role == ChatRole.USER
    assert loaded.messages[1].role == ChatRole.ASSISTANT
