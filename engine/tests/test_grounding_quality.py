"""
Unit tests for Ragger.ai v1.1 Grounding Quality and Evidence Sufficiency Gate.
Verifies:
1. In-domain factual answering directly synthesized from chunks.
2. Zero boilerplate phrases ("operational specifications" eliminated).
3. Out-of-domain (OOD) evidence gate refusal without hallucination.
4. Clean disclaimer text with zero unverified citations.
"""

import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import pytest

from ragger_engine.builder.models import BuildManifest, Chunk, ChunkMetadata, ChunkType
from ragger_engine.builder.storage.local_flat_store import LocalFlatVectorStore
from ragger_engine.generation.models import ChatQueryRequest, CitationValidationStatus
from ragger_engine.generation.service import GenerationService
from ragger_engine.retrieval.service import RetrievalService


@pytest.fixture
def textbook_workspace(tmp_path: Path):
    """Creates a mock workspace with the textbook young seagull chunk."""
    build_id = "bld_textbook_test"
    build_dir = tmp_path / "builds" / build_id
    index_dir = build_dir / "index"
    index_dir.mkdir(parents=True, exist_ok=True)

    seagull_text = (
        "The young seagull was alone on his ledge. His two brothers and his sister had already "
        "flown away the day before. He had been afraid to fly with them. Somehow, when he had taken "
        "a little run forward to the brink of the ledge and attempted to flap his wings, he became afraid. "
        "The great expanse of sea stretched down beneath, and it was such a long way down - miles down. "
        "He felt certain that his wings would never support him; so he bent his head and ran away back "
        "to the little hole under the ledge where he slept at night."
    )

    chunks = [
        Chunk(
            chunk_id="chk_seagull_01",
            source_id="src_tb_1",
            text=seagull_text,
            chunk_type=ChunkType.STANDARD_PARAGRAPH,
            metadata=ChunkMetadata(
                source_id="src_tb_1",
                source_name="Class_10_English.pdf",
                chunk_index=0,
                token_count=100,
                page_number=6,
                heading_path=["Prose", "His First Flight"],
            ),
            token_count=100,
        )
    ]
    vectors = [[0.05] * 384]

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
        "source_ids": ["src_tb_1"],
        "source_hashes": {"src_tb_1": "b" * 64},
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

    with open(tmp_path / "active_build.json", "w", encoding="utf-8") as f:
        f.write('{"active_build_id": "bld_textbook_test", "manifest_hash": "%s"}' % manifest.manifest_hash)

    with open(tmp_path / "generation_config.json", "w", encoding="utf-8") as f:
        f.write('{"provider": "test_deterministic", "model_name": "test_deterministic", "temperature": 0.1, "max_tokens": 1024}')

    ret_svc = RetrievalService(workspace_dir=tmp_path)
    gen_svc = GenerationService(workspace_dir=tmp_path, retrieval_service=ret_svc)
    return gen_svc


def test_in_domain_textbook_grounded_answer(textbook_workspace, monkeypatch):
    """Verifies that in-domain question is answered factually with exact citation and zero boilerplate."""
    monkeypatch.setenv("RAGGER_ALLOW_TEST_LLM", "1")
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EMBEDDINGS", "1")
    gen_svc = textbook_workspace

    req = ChatQueryRequest(query="Why was the young seagull afraid to fly?")
    resp = asyncio.run(gen_svc.generate(req, workspace_id="default"))

    # Must be factual
    assert resp.has_insufficient_evidence is False
    assert "wings would not support him" in resp.answer.lower()
    assert "expanse of sea" in resp.answer.lower()

    # Zero boilerplate
    assert "operational specifications" not in resp.answer.lower()

    # Must have verified citation
    assert len(resp.valid_citations) == 1
    assert resp.valid_citations[0].chunk_id == "chk_seagull_01"
    assert resp.valid_citations[0].page_number == 6
    assert resp.citation_validation_status == CitationValidationStatus.VERIFIED


def test_out_of_domain_evidence_gate_refusal(textbook_workspace, monkeypatch):
    """Verifies that out-of-domain question triggers evidence gate disclaimer with zero citations."""
    monkeypatch.setenv("RAGGER_ALLOW_TEST_LLM", "1")
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EMBEDDINGS", "1")
    gen_svc = textbook_workspace

    req = ChatQueryRequest(query="What is the capital of France?")
    resp = asyncio.run(gen_svc.generate(req, workspace_id="default"))

    # Must trigger disclaimer
    assert resp.has_insufficient_evidence is True
    assert "couldn't find information about" in resp.answer.lower()
    assert "capital of france" in resp.answer.lower()
    assert "try asking something related to your selected sources" in resp.answer.lower()

    # Must have zero citations
    assert len(resp.valid_citations) == 0
    assert len(resp.unverified_citation_keys) == 0
    assert resp.citation_validation_status == CitationValidationStatus.NO_CITATIONS
