"""
Integration & unit tests for EvaluationService.
Verifies end-to-end evaluation execution, zero chat-session pollution,
concurrency safety (409), build integrity gate (409), late cancellation,
and report card persistence.
"""

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import pytest

from ragger_engine.builder.models import BuildManifest, Chunk, ChunkMetadata, ChunkType
from ragger_engine.builder.storage.local_flat_store import LocalFlatVectorStore
from ragger_engine.evaluation.exceptions import (
    EvaluationAlreadyRunningError,
    EvaluationBuildChangedError,
    EvaluationNotFoundError,
)
from ragger_engine.evaluation.models import (
    EvaluationConfig,
    EvaluationRunRequest,
    EvaluationState,
)
from ragger_engine.evaluation.providers.test_judge import TestDeterministicEvalJudge
from ragger_engine.evaluation.service import EvaluationService
from ragger_engine.evaluation.snapshot import capture_build_snapshot, verify_build_integrity
from ragger_engine.generation.providers.testing import TestDeterministicLLMProvider
from ragger_engine.generation.service import GenerationService
from ragger_engine.retrieval.service import RetrievalService


def setup_eval_workspace(workspace_dir: Path) -> tuple[EvaluationService, GenerationService]:
    """Creates a valid active build with 4 chunks across 2 sources and returns EvaluationService."""
    build_id = "bld_eval_test"
    build_dir = workspace_dir / "builds" / build_id
    index_dir = build_dir / "index"
    index_dir.mkdir(parents=True, exist_ok=True)

    chunks = [
        Chunk(
            chunk_id="chk_corp_01",
            source_id="src_policy",
            text="The standard corporate annual leave allowance is 25 paid vacation days per calendar year.",
            chunk_type=ChunkType.STANDARD_PARAGRAPH,
            metadata=ChunkMetadata(
                source_id="src_policy",
                source_name="policy.pdf",
                chunk_index=0,
                token_count=16,
                page_number=1,
                heading_path=["HR Policy", "Vacation"],
            ),
            token_count=16,
        ),
        Chunk(
            chunk_id="chk_corp_02",
            source_id="src_policy",
            text="Unused annual leave up to 5 days may be carried forward into the following quarter.",
            chunk_type=ChunkType.STANDARD_PARAGRAPH,
            metadata=ChunkMetadata(
                source_id="src_policy",
                source_name="policy.pdf",
                chunk_index=1,
                token_count=16,
                page_number=1,
                heading_path=["HR Policy", "Carryover"],
            ),
            token_count=16,
        ),
        Chunk(
            chunk_id="chk_sec_01",
            source_id="src_security",
            text="Hardware security keys with FIDO2 WebAuthn authentication are mandatory for production server access.",
            chunk_type=ChunkType.STANDARD_PARAGRAPH,
            metadata=ChunkMetadata(
                source_id="src_security",
                source_name="security.md",
                chunk_index=0,
                token_count=16,
                page_number=1,
                heading_path=["Security Controls", "Authentication"],
            ),
            token_count=16,
        ),
        Chunk(
            chunk_id="chk_sec_02",
            source_id="src_security",
            text="All administrative SSH sessions must be established through the dedicated bastion jump host.",
            chunk_type=ChunkType.STANDARD_PARAGRAPH,
            metadata=ChunkMetadata(
                source_id="src_security",
                source_name="security.md",
                chunk_index=1,
                token_count=15,
                page_number=2,
                heading_path=["Security Controls", "Bastion"],
            ),
            token_count=15,
        ),
    ]
    vectors = [[0.1] * 384 for _ in range(4)]

    store = LocalFlatVectorStore()
    store.add_chunks(chunks, vectors)
    store.persist(index_dir)

    now = datetime.now(timezone.utc)
    manifest_dict = {
        "manifest_id": f"man_{build_id}",
        "workspace_id": "ws_eval",
        "build_id": build_id,
        "config_id": "cfg_eval001",
        "config_version": 1,
        "config_hash": "a" * 64,
        "source_ids": ["src_policy", "src_security"],
        "source_hashes": {"src_policy": "p" * 64, "src_security": "s" * 64},
        "approved_architecture": "hybrid_rag",
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
    llm_provider = TestDeterministicLLMProvider()
    gen_svc = GenerationService(
        workspace_dir=workspace_dir,
        retrieval_service=retrieval_svc,
        provider_override=llm_provider,
    )

    eval_config = EvaluationConfig(
        judge_provider="test",
        judge_model_name="test-judge",
        temperature=0.0,
        max_tokens=256,
        default_sample_size=4,
        sampling_seed=42,
        retrieval_top_k=3,
    )
    with open(workspace_dir / "evaluation_config.json", "w", encoding="utf-8") as f:
        f.write(eval_config.model_dump_json(indent=2))

    judge = TestDeterministicEvalJudge()
    eval_svc = EvaluationService(
        workspace_dir=workspace_dir,
        workspace_id="ws_eval",
        retrieval_service=retrieval_svc,
        generation_service=gen_svc,
        judge_override=judge,
    )
    return eval_svc, gen_svc


@pytest.mark.asyncio
async def test_full_evaluation_run_and_zero_chat_pollution(tmp_path, monkeypatch):
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EMBEDDINGS", "1")
    monkeypatch.setenv("RAGGER_ALLOW_TEST_LLM", "1")
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EVAL", "1")

    workspace_dir = tmp_path / "ws_eval"
    workspace_dir.mkdir()
    eval_svc, gen_svc = setup_eval_workspace(workspace_dir)

    # Initial state: chat_sessions/ should be empty
    assert len(list(gen_svc.sessions_dir.glob("*.json"))) == 0

    req = EvaluationRunRequest(sample_size=4, sampling_seed=42)
    report = await eval_svc.run_evaluation(req)

    # 1. Report card assertions
    assert report.eval_id.startswith("eval_")
    assert report.workspace_id == "ws_eval"
    assert report.quality_score >= 0.0
    assert report.quality_score <= 100.0
    assert len(report.probe_results) == 4
    assert report.deterministic_metrics.source_coverage > 0.0
    assert report.build_snapshot.build_id == "bld_eval_test"

    # 2. ZERO chat history pollution: verify no chat session files were written to disk
    persisted_sessions = list(gen_svc.sessions_dir.glob("*.json"))
    assert len(persisted_sessions) == 0, f"Expected 0 chat sessions, found: {persisted_sessions}"

    # 3. Report file existence on disk
    report_file = eval_svc.evaluations_dir / f"{report.eval_id}.json"
    assert report_file.exists()

    # 4. Report list & get
    reports = eval_svc.list_reports()
    assert len(reports) == 1
    assert reports[0]["eval_id"] == report.eval_id

    loaded_report = eval_svc.get_report(report.eval_id)
    assert loaded_report.eval_id == report.eval_id
    assert loaded_report.quality_score == report.quality_score


@pytest.mark.asyncio
async def test_concurrency_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EMBEDDINGS", "1")
    monkeypatch.setenv("RAGGER_ALLOW_TEST_LLM", "1")
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EVAL", "1")

    workspace_dir = tmp_path / "ws_eval"
    workspace_dir.mkdir()
    eval_svc, _ = setup_eval_workspace(workspace_dir)

    req = EvaluationRunRequest(sample_size=4, sampling_seed=42)
    eval_id = await eval_svc.start_evaluation(req)

    # Attempting to start a second run while active must raise EvaluationAlreadyRunningError (409)
    with pytest.raises(EvaluationAlreadyRunningError) as exc_info:
        await eval_svc.start_evaluation(req)
    assert exc_info.value.code == "EVALUATION_ALREADY_RUNNING"

    # Await the first task completion
    for _ in range(100):
        progress = eval_svc.get_progress(eval_id)
        if progress.state in [EvaluationState.COMPLETED, EvaluationState.FAILED, EvaluationState.CANCELLED]:
            break
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_build_integrity_gate_on_mutation(tmp_path, monkeypatch):
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EMBEDDINGS", "1")
    monkeypatch.setenv("RAGGER_ALLOW_TEST_LLM", "1")
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EVAL", "1")

    workspace_dir = tmp_path / "ws_eval"
    workspace_dir.mkdir()
    setup_eval_workspace(workspace_dir)

    snapshot = capture_build_snapshot(workspace_dir, "ws_eval")

    # Mutate active_build.json pointer
    active_pointer = workspace_dir / "active_build.json"
    with open(active_pointer, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["active_build_id"] = "bld_changed_midway"
    with open(active_pointer, "w", encoding="utf-8") as f:
        json.dump(data, f)

    with pytest.raises(EvaluationBuildChangedError) as exc_info:
        verify_build_integrity(workspace_dir, snapshot)
    assert exc_info.value.code == "EVALUATION_BUILD_CHANGED"


@pytest.mark.asyncio
async def test_late_cancellation_immutable(tmp_path, monkeypatch):
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EMBEDDINGS", "1")
    monkeypatch.setenv("RAGGER_ALLOW_TEST_LLM", "1")
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EVAL", "1")

    workspace_dir = tmp_path / "ws_eval"
    workspace_dir.mkdir()
    eval_svc, _ = setup_eval_workspace(workspace_dir)

    req = EvaluationRunRequest(sample_size=3, sampling_seed=42)
    report = await eval_svc.run_evaluation(req)

    # Late cancel on finished run must return already_completed
    res = await eval_svc.cancel_evaluation(report.eval_id)
    assert res.get("status") == "already_completed"
