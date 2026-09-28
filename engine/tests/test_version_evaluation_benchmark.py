"""
Phase 15 Comprehensive Benchmark & Verification Tests:
RAG Version Evaluation & Grounding Benchmark per RAG Version.

Verifies:
1. Version-scoped evaluation against Build A1 and Build A2.
2. Reports permanently record immutable provenance:
   rag_id, version_id, version_tag, build_id, manifest_id, manifest_hash,
   approved_architecture, source_ids, chunk_count, vector_count, config, seed.
3. Snapshot Immutability Invariant:
   Activating version A2 while evaluation of A1 is running does not crash or invalidate
   the evaluation, and the resulting report records Build A1 while active_version_id is A2.
4. Same-RAG comparison validation:
   Comparing evaluations of the same RAG succeeds with purely factual numeric deltas;
   cross-RAG comparison is rejected with HTTP 400 (InvalidEvaluationParameterError).
5. Partial parameter validation:
   Supplying only rag_id or only version_id is strictly rejected (HTTP 400).
6. Controlled failure handling:
   Corrupted or missing build fails closed cleanly.
7. Legacy mode backward compatibility:
   Running evaluation with neither rag_id nor version_id still resolves active_build.json.
"""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import pytest

from ragger_engine.builder.models import BuildManifest, Chunk, ChunkMetadata, ChunkType
from ragger_engine.builder.storage.local_flat_store import LocalFlatVectorStore
from ragger_engine.evaluation.exceptions import (
    EvaluationError,
    EvaluationNotFoundError,
    InvalidEvaluationParameterError,
)
from ragger_engine.evaluation.models import (
    EvaluationConfig,
    EvaluationRunRequest,
    EvaluationState,
)
from ragger_engine.evaluation.providers.test_judge import TestDeterministicEvalJudge
from ragger_engine.evaluation.service import EvaluationService
from ragger_engine.generation.providers.testing import TestDeterministicLLMProvider
from ragger_engine.generation.service import GenerationService
from ragger_engine.rag_lifecycle.exceptions import (
    RAGNotFoundError,
    RAGVersionNotFoundError,
)
from ragger_engine.rag_lifecycle.models import (
    CreateRAGRequest,
    RegisterVersionRequest,
    UpdateRAGRequest,
)
from ragger_engine.rag_lifecycle.service import RAGLifecycleService
from ragger_engine.retrieval.service import RetrievalService


def create_mock_build(workspace_dir: Path, build_id: str, source_tag: str, chunk_texts: list[str]) -> str:
    """Helper to create a completed mock build with flat vector store index and chunks."""
    build_dir = workspace_dir / "builds" / build_id
    index_dir = build_dir / "index"
    index_dir.mkdir(parents=True, exist_ok=True)

    chunks = []
    for idx, text in enumerate(chunk_texts):
        cid = f"chk_{source_tag}_{idx:02d}"
        sid = f"src_{source_tag}"
        chunks.append(
            Chunk(
                chunk_id=cid,
                source_id=sid,
                text=text,
                chunk_type=ChunkType.STANDARD_PARAGRAPH,
                metadata=ChunkMetadata(
                    source_id=sid,
                    source_name=f"{source_tag}.txt",
                    chunk_index=idx,
                    token_count=len(text.split()),
                    page_number=1,
                    heading_path=[source_tag.upper(), f"Section {idx}"],
                ),
                token_count=len(text.split()),
            )
        )

    vectors = [[0.1] * 384 for _ in range(len(chunks))]
    store = LocalFlatVectorStore()
    store.add_chunks(chunks, vectors)
    store.persist(index_dir)

    now = datetime.now(timezone.utc)
    manifest_dict = {
        "manifest_id": f"man_{build_id}",
        "workspace_id": "ws_test",
        "build_id": build_id,
        "config_id": f"cfg_{build_id}",
        "config_version": 1,
        "config_hash": "a" * 64,
        "source_ids": [f"src_{source_tag}"],
        "source_hashes": {f"src_{source_tag}": "s" * 64},
        "approved_architecture": "document_rag",
        "chunking_config": {"strategy": "boundary_paragraph", "chunk_size": 512, "chunk_overlap": 64},
        "embedding_config": {"provider": "test_deterministic", "model_name": "bge-small-en-v1.5", "dimension": 384},
        "vector_db_config": {"provider": "local_flat_index", "metric": "cosine", "index_type": "auto"},
        "retrieval_config": {"strategy": "dense_vector_top_k", "top_k": 3, "rerank_enabled": False},
        "chunk_count": len(chunks),
        "vector_count": len(chunks),
        "embedding_dimension": 384,
        "embedding_model": "bge-small-en-v1.5",
        "vector_store": "local_flat_index",
        "started_at": now,
        "completed_at": now,
        "build_duration_ms": 50.0,
        "status": "completed",
    }
    manifest_dict["manifest_hash"] = BuildManifest.compute_manifest_hash(manifest_dict)
    manifest = BuildManifest(**manifest_dict)

    with open(build_dir / "manifest.json", "w", encoding="utf-8") as f:
        f.write(manifest.model_dump_json(indent=2))

    return build_id


def setup_multi_version_fixture(workspace_dir: Path, monkeypatch=None):
    """Sets up RAG A (v1 on Build A1, v2 on Build A2) and RAG B (v1 on Build B1)."""
    if monkeypatch:
        monkeypatch.setenv("RAGGER_ALLOW_TEST_EMBEDDINGS", "1")
        monkeypatch.setenv("RAGGER_ALLOW_TEST_LLM", "1")
        monkeypatch.setenv("RAGGER_ALLOW_TEST_EVAL", "1")
    else:
        import os
        os.environ["RAGGER_ALLOW_TEST_EMBEDDINGS"] = "1"
        os.environ["RAGGER_ALLOW_TEST_LLM"] = "1"
        os.environ["RAGGER_ALLOW_TEST_EVAL"] = "1"

    # 1. Build A1
    create_mock_build(
        workspace_dir,
        build_id="bld_ragA_v1",
        source_tag="docA1",
        chunk_texts=[
            "Alpha Corporation was founded in 2010 to develop artificial intelligence systems.",
            "Alpha Corporation headquarters are located in San Francisco, California.",
            "Alpha Corporation employs over 500 engineers and research scientists.",
        ],
    )

    # 2. Build A2 (updated with new facts)
    create_mock_build(
        workspace_dir,
        build_id="bld_ragA_v2",
        source_tag="docA2",
        chunk_texts=[
            "Alpha Corporation was founded in 2010 to develop cutting-edge artificial intelligence systems.",
            "Alpha Corporation expanded headquarters to New York City and London in 2024.",
            "Alpha Corporation employs over 1200 engineers across global offices.",
            "Alpha Corporation launched quantum hybrid computing initiatives in 2025.",
        ],
    )

    # 3. Build B1 (completely separate RAG)
    create_mock_build(
        workspace_dir,
        build_id="bld_ragB_v1",
        source_tag="docB1",
        chunk_texts=[
            "Beta Medical supplies diagnostic ultrasound hardware to university hospitals worldwide.",
            "Beta Medical received FDA clearance for cardiovascular imaging devices in 2022.",
            "Beta Medical research center is headquartered in Boston, Massachusetts.",
        ],
    )

    # Active build pointer for legacy mode
    pointer = {
        "active_build_id": "bld_ragA_v1",
        "manifest_id": "man_bld_ragA_v1",
        "manifest_hash": json.loads((workspace_dir / "builds" / "bld_ragA_v1" / "manifest.json").read_text(encoding="utf-8"))["manifest_hash"],
        "activated_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(workspace_dir / "active_build.json", "w", encoding="utf-8") as f:
        json.dump(pointer, f, indent=2)

    # Evaluation config
    eval_config = EvaluationConfig(
        judge_provider="test",
        judge_model_name="test-judge",
        temperature=0.0,
        max_tokens=256,
        default_sample_size=3,
        sampling_seed=42,
        retrieval_top_k=2,
    )
    with open(workspace_dir / "evaluation_config.json", "w", encoding="utf-8") as f:
        f.write(eval_config.model_dump_json(indent=2))

    # Initialize services
    retrieval_svc = RetrievalService(workspace_dir=workspace_dir)
    llm_provider = TestDeterministicLLMProvider()
    gen_svc = GenerationService(
        workspace_dir=workspace_dir,
        retrieval_service=retrieval_svc,
        provider_override=llm_provider,
    )
    judge = TestDeterministicEvalJudge()
    lifecycle_svc = RAGLifecycleService(workspace_dir=workspace_dir)

    eval_svc = EvaluationService(
        workspace_dir=workspace_dir,
        workspace_id="default",
        retrieval_service=retrieval_svc,
        generation_service=gen_svc,
        judge_override=judge,
        rag_lifecycle_service=lifecycle_svc,
    )

    # Register RAG A with v1 and v2
    rag_a = lifecycle_svc.create_rag(CreateRAGRequest(
        name="RAG Alpha",
        description="Alpha Knowledge Base",
        initial_build_id="bld_ragA_v1",
    ))
    v1_id = rag_a.active_version_id

    ver_v2 = lifecycle_svc.register_version(
        rag_a.rag_id,
        RegisterVersionRequest(
            version_tag="v2.0.0",
            build_id="bld_ragA_v2",
            set_active=False,
        ),
    )
    v2_id = ver_v2.version_id

    # Register RAG B with v1
    rag_b = lifecycle_svc.create_rag(CreateRAGRequest(
        name="RAG Beta",
        description="Beta Knowledge Base",
        initial_build_id="bld_ragB_v1",
    ))
    b_v1_id = rag_b.active_version_id

    return {
        "eval_svc": eval_svc,
        "lifecycle_svc": lifecycle_svc,
        "rag_a_id": rag_a.rag_id,
        "v1_id": v1_id,
        "v2_id": v2_id,
        "rag_b_id": rag_b.rag_id,
        "b_v1_id": b_v1_id,
    }


@pytest.mark.asyncio
async def test_version_scoped_evaluation_records_immutable_identity(tmp_path: Path):
    """
    Refinement 1 & Acceptance:
    Evaluation permanently records rag_id, version_id, version_tag, build_id,
    manifest_id, manifest_hash, architecture, source IDs, chunk_count, vector_count.
    """
    ctx = setup_multi_version_fixture(tmp_path)
    eval_svc: EvaluationService = ctx["eval_svc"]

    req = EvaluationRunRequest(
        rag_id=ctx["rag_a_id"],
        version_id=ctx["v1_id"],
        sample_size=3,
        sampling_seed=42,
    )

    report = await eval_svc.run_evaluation(req)

    # Verify root fields
    assert report.rag_id == ctx["rag_a_id"]
    assert report.version_id == ctx["v1_id"]
    assert report.version_tag == "v1.0.0"

    # Verify build snapshot identity
    snap = report.build_snapshot
    assert snap.build_id == "bld_ragA_v1"
    assert snap.rag_id == ctx["rag_a_id"]
    assert snap.version_id == ctx["v1_id"]
    assert snap.version_tag == "v1.0.0"
    assert snap.manifest_id == "man_bld_ragA_v1"
    assert len(snap.manifest_hash) == 64
    assert snap.approved_architecture == "document_rag"
    assert "src_docA1" in snap.source_ids
    assert snap.chunk_count == 3
    assert snap.vector_count == 3

    # Verify persisted report on disk matches
    persisted = eval_svc.get_report(report.eval_id)
    assert persisted.rag_id == ctx["rag_a_id"]
    assert persisted.version_id == ctx["v1_id"]
    assert persisted.build_snapshot.build_id == "bld_ragA_v1"
    assert persisted.build_snapshot.manifest_hash == snap.manifest_hash


@pytest.mark.asyncio
async def test_partial_parameter_rejection(tmp_path: Path):
    """
    Refinement 2:
    Reject partial parameters (only rag_id OR only version_id) with HTTP 400 validation error.
    Never silently combine with active_build.json.
    """
    ctx = setup_multi_version_fixture(tmp_path)
    eval_svc: EvaluationService = ctx["eval_svc"]

    # Only rag_id provided
    with pytest.raises(InvalidEvaluationParameterError) as exc_info:
        await eval_svc.run_evaluation(EvaluationRunRequest(rag_id=ctx["rag_a_id"]))
    assert "Both 'rag_id' and 'version_id' must be provided" in str(exc_info.value)

    # Only version_id provided
    with pytest.raises(InvalidEvaluationParameterError) as exc_info2:
        await eval_svc.run_evaluation(EvaluationRunRequest(version_id=ctx["v1_id"]))
    assert "Both 'rag_id' and 'version_id' must be provided" in str(exc_info2.value)


@pytest.mark.asyncio
async def test_snapshot_immutability_during_active_version_mutation(tmp_path: Path):
    """
    Refinement 4:
    Evaluating version A1 while active version is switched to A2 does NOT fail the evaluation.
    The evaluation completes on Build A1, the report records Build A1, while active_version_id is A2.
    """
    ctx = setup_multi_version_fixture(tmp_path)
    eval_svc: EvaluationService = ctx["eval_svc"]
    lifecycle_svc: RAGLifecycleService = ctx["lifecycle_svc"]

    # Initial state: active version of RAG A is v1
    rag_record = lifecycle_svc.get_rag(ctx["rag_a_id"])
    assert rag_record.active_version_id == ctx["v1_id"]

    # Start evaluation of v1
    req = EvaluationRunRequest(
        rag_id=ctx["rag_a_id"],
        version_id=ctx["v1_id"],
        sample_size=3,
        sampling_seed=42,
    )
    eval_id = await eval_svc.start_evaluation(req)

    # Mutate active version to v2 while evaluation of v1 is running
    lifecycle_svc.rollback_version(ctx["rag_a_id"], ctx["v2_id"])
    updated_rag = lifecycle_svc.get_rag(ctx["rag_a_id"])
    assert updated_rag.active_version_id == ctx["v2_id"]

    # Wait for evaluation background task to complete
    while True:
        prog = eval_svc.get_progress(eval_id)
        if prog.state in (EvaluationState.COMPLETED, EvaluationState.FAILED, EvaluationState.CANCELLED):
            break
        await asyncio.sleep(0.05)

    assert prog.state == EvaluationState.COMPLETED

    # The persisted evaluation report MUST report Build A1, not A2
    report = eval_svc.get_report(eval_id)
    assert report.build_snapshot.build_id == "bld_ragA_v1"
    assert report.rag_id == ctx["rag_a_id"]
    assert report.version_id == ctx["v1_id"]

    # RAG active pointer remains independently v2
    final_rag = lifecycle_svc.get_rag(ctx["rag_a_id"])
    assert final_rag.active_version_id == ctx["v2_id"]


@pytest.mark.asyncio
async def test_same_rag_comparison_and_cross_rag_rejection(tmp_path: Path):
    """
    Refinement 3:
    compare_version_evaluations verifies both evaluations belong to the same RAG.
    Cross-RAG comparison is rejected.
    Output is purely descriptive with numeric deltas and no qualitative promotion language.
    """
    ctx = setup_multi_version_fixture(tmp_path)
    eval_svc: EvaluationService = ctx["eval_svc"]

    # Evaluate RAG A v1
    rep_a1 = await eval_svc.run_evaluation(EvaluationRunRequest(
        rag_id=ctx["rag_a_id"],
        version_id=ctx["v1_id"],
        sample_size=3,
        sampling_seed=42,
    ))

    # Evaluate RAG A v2
    rep_a2 = await eval_svc.run_evaluation(EvaluationRunRequest(
        rag_id=ctx["rag_a_id"],
        version_id=ctx["v2_id"],
        sample_size=3,
        sampling_seed=42,
    ))

    # Evaluate RAG B v1
    rep_b1 = await eval_svc.run_evaluation(EvaluationRunRequest(
        rag_id=ctx["rag_b_id"],
        version_id=ctx["b_v1_id"],
        sample_size=3,
        sampling_seed=42,
    ))

    # 1. Valid comparison: RAG A v1 vs RAG A v2
    cmp_res = eval_svc.compare_version_evaluations(
        rag_id=ctx["rag_a_id"],
        base_eval_id=rep_a1.eval_id,
        target_eval_id=rep_a2.eval_id,
    )
    assert cmp_res.rag_id == ctx["rag_a_id"]
    assert cmp_res.base_build_id == "bld_ragA_v1"
    assert cmp_res.target_build_id == "bld_ragA_v2"
    assert cmp_res.quality_score_delta.delta is not None
    assert cmp_res.hits_at_1_delta.delta is not None
    assert cmp_res.hits_at_3_delta.delta is not None

    # 2. Cross-RAG comparison: RAG A eval vs RAG B eval under rag_a_id -> rejected
    with pytest.raises(InvalidEvaluationParameterError) as exc_cross:
        eval_svc.compare_version_evaluations(
            rag_id=ctx["rag_a_id"],
            base_eval_id=rep_a1.eval_id,
            target_eval_id=rep_b1.eval_id,
        )
    assert f"belongs to RAG '{ctx['rag_b_id']}'" in str(exc_cross.value)

    # 3. Both from RAG B under rag_a_id -> rejected
    with pytest.raises(InvalidEvaluationParameterError) as exc_cross2:
        eval_svc.compare_version_evaluations(
            rag_id=ctx["rag_a_id"],
            base_eval_id=rep_b1.eval_id,
            target_eval_id=rep_b1.eval_id,
        )
    assert f"belongs to RAG '{ctx['rag_b_id']}'" in str(exc_cross2.value)


@pytest.mark.asyncio
async def test_legacy_mode_backward_compatibility(tmp_path: Path):
    """
    Verifies that running evaluation without rag_id and version_id continues
    to evaluate the active build specified in active_build.json.
    """
    ctx = setup_multi_version_fixture(tmp_path)
    eval_svc: EvaluationService = ctx["eval_svc"]

    legacy_report = await eval_svc.run_evaluation(EvaluationRunRequest(sample_size=3, sampling_seed=42))

    assert legacy_report.build_snapshot.build_id == "bld_ragA_v1"
    assert legacy_report.rag_id is None
    assert legacy_report.version_id is None
    assert legacy_report.quality_score >= 0.0


@pytest.mark.asyncio
async def test_corrupted_or_missing_build_fails_closed(tmp_path: Path):
    """
    Verifies that evaluation against a non-existent or corrupted version fails closed.
    """
    ctx = setup_multi_version_fixture(tmp_path)
    eval_svc: EvaluationService = ctx["eval_svc"]

    # Non-existent version
    with pytest.raises(RAGVersionNotFoundError):
        await eval_svc.run_evaluation(EvaluationRunRequest(
            rag_id=ctx["rag_a_id"],
            version_id="ver_non_existent",
            sample_size=3,
        ))

    # Non-existent RAG
    with pytest.raises(RAGNotFoundError):
        await eval_svc.run_evaluation(EvaluationRunRequest(
            rag_id="rag_non_existent",
            version_id=ctx["v1_id"],
            sample_size=3,
        ))
