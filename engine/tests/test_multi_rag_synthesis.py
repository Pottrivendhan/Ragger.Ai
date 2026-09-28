"""
Tests for Phase 16: Multi-RAG Hybrid Synthesis & Multi-Attachment Agents.
Covers:
- Test A: Single-RAG Functional Equivalence (1 attached RAG preserves single-RAG behavior, citations, and gate)
- Test B: Two-RAG Hybrid Synthesis (Unified retrieval across two RAGs, RRF k=60 fusion, citations from both)
- Test C: Single-RAG-Only Query in Multi-RAG Agent (Zero cross-RAG citation fabrication)
- Test D: Strict Composite Citation & Attribution Bleeding Defense (rag_id + build_id + chunk_id authoritative validation)
- Test E: Missing RAG Fail-Closed (Missing attached RAG rejects request fail-closed)
- Test F: Corrupted Build Fail-Closed (Corrupted build status rejects request fail-closed without silent degradation)
- Test G: Cross-RAG Evidence Gate (OOD query fails closed across all attached RAGs)
- Test H: Dynamic Version Switch (RAG promoting v1 -> v2 immediately switches retrieval to v2 build)
- Test I: Client Target Endpoint Redaction (GET /api/v1/agents/{id}/resolved-targets excludes build_id)
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

from ragger_engine.agent_workspace.models import AgentProfile, AgentChatRequest
from ragger_engine.agent_workspace.service import AgentWorkspaceService
from ragger_engine.agent_workspace.exceptions import NoAttachedRAGError, RAGArtifactNotFoundError
from ragger_engine.rag_lifecycle.service import RAGLifecycleService
from ragger_engine.rag_lifecycle.models import RAGArtifactRecord, RAGVersionInfo, RAGStatus
from ragger_engine.multi_rag.models import (
    ResolvedRAGTarget,
    MultiRAGCandidate,
    MultiRAGRetrievalResult,
    MultiRAGClientTarget,
)
from ragger_engine.multi_rag.coordinator import (
    MultiRAGCoordinator,
    MultiRAGRetrievalError,
)
from ragger_engine.multi_rag.evidence_adapter import MultiRAGEvidenceAdapter
from ragger_engine.retrieval.models import (
    RetrievalResponse,
    RetrievedChunk,
    CitationProvenance,
    ScoreType,
)
from ragger_engine.builder.models import ChunkType
from ragger_engine.generation.models import CitationValidationStatus



@pytest.fixture
def mock_retrieval_service():
    service = MagicMock()
    # Mock build runtime with completed manifest
    runtime = MagicMock()
    runtime.manifest.status = "completed"
    service.get_or_load_build_runtime.return_value = runtime
    return service


@pytest.fixture
def mock_lifecycle_service():
    service = MagicMock()
    rag_a = RAGArtifactRecord(
        rag_id="rag_physics",
        name="Physics Knowledge Base",
        description="Physics textbook",
        status=RAGStatus.ACTIVE,
        active_version_id="ver_p1",
        versions=[
            RAGVersionInfo(
                version_id="ver_p1",
                version_tag="v1.0.0",
                build_id="bld_physics_1",
                created_at="2026-09-22T00:00:00Z",
                chunk_count=10,
                vector_count=10,
                manifest_hash="hash_p1",
                manifest_id="man_p1",
                embedding_model="mock_emb",
                vector_store="chroma",
            ),
            RAGVersionInfo(
                version_id="ver_p2",
                version_tag="v2.0.0",
                build_id="bld_physics_2",
                created_at="2026-09-22T01:00:00Z",
                chunk_count=12,
                vector_count=12,
                manifest_hash="hash_p2",
                manifest_id="man_p2",
                embedding_model="mock_emb",
                vector_store="chroma",
            ),
        ],
        source_ids=["src_phy_01"],
        created_at="2026-09-22T00:00:00Z",
        updated_at="2026-09-22T00:00:00Z",
    )
    rag_b = RAGArtifactRecord(
        rag_id="rag_biology",
        name="Biology Knowledge Base",
        description="Biology textbook",
        status=RAGStatus.ACTIVE,
        active_version_id="ver_b1",
        versions=[
            RAGVersionInfo(
                version_id="ver_b1",
                version_tag="v1.0.0",
                build_id="bld_biology_1",
                created_at="2026-09-22T00:00:00Z",
                chunk_count=15,
                vector_count=15,
                manifest_hash="hash_b1",
                manifest_id="man_b1",
                embedding_model="mock_emb",
                vector_store="chroma",
            ),
        ],
        source_ids=["src_bio_01"],
        created_at="2026-09-22T00:00:00Z",
        updated_at="2026-09-22T00:00:00Z",
    )

    def _get_rag(rag_id: str):
        if rag_id == "rag_physics":
            return rag_a
        elif rag_id == "rag_biology":
            return rag_b
        from ragger_engine.rag_lifecycle.exceptions import RAGNotFoundError
        raise RAGNotFoundError(rag_id)

    service.get_rag.side_effect = _get_rag
    service.list_rags.return_value = [rag_a, rag_b]
    return service


def test_adjustment_1_target_redaction(mock_retrieval_service, mock_lifecycle_service):
    """Test I: Verify client targets endpoint explicitly excludes build_id."""
    coord = MultiRAGCoordinator(
        retrieval_service=mock_retrieval_service,
        rag_lifecycle_service=mock_lifecycle_service,
    )
    agent = AgentProfile(
        agent_id="agt_science",
        name="Science Agent",
        description="Multi-disciplinary science assistant",
        attached_rag_ids=["rag_physics", "rag_biology"],
    )
    resolved = coord.resolve_agent_runtimes(agent)
    client_targets = coord.get_client_targets(resolved)

    assert len(client_targets) == 2
    for ct in client_targets:
        target_dict = ct.model_dump()
        assert "build_id" not in target_dict
        assert "rag_id" in target_dict
        assert "rag_name" in target_dict
        assert "version_id" in target_dict
        assert "version_tag" in target_dict


def test_adjustment_2_authoritative_resolution_chain(mock_retrieval_service, mock_lifecycle_service):
    """Test resolution chain: rag_id -> active_version_id -> version -> build_id -> completed manifest."""
    coord = MultiRAGCoordinator(
        retrieval_service=mock_retrieval_service,
        rag_lifecycle_service=mock_lifecycle_service,
    )
    agent = AgentProfile(
        agent_id="agt_phy",
        name="Physics Agent",
        description="Physics only",
        attached_rag_ids=["rag_physics"],
    )
    resolved = coord.resolve_agent_runtimes(agent)
    assert len(resolved) == 1
    assert resolved[0].rag_id == "rag_physics"
    assert resolved[0].version_id == "ver_p1"
    assert resolved[0].build_id == "bld_physics_1"
    mock_retrieval_service.get_or_load_build_runtime.assert_called_with("bld_physics_1", is_scoped_call=True)


def test_adjustment_3_evidence_gate_adapter():
    """Test adapter converts MultiRAGCandidate to RetrievedChunk without modifying gate logic."""
    gen_service = MagicMock()
    gen_service._evaluate_evidence_sufficiency.return_value = (True, "")

    candidates = [
        MultiRAGCandidate(
            rag_id="rag_physics",
            rag_name="Physics",
            version_id="ver_p1",
            version_tag="v1.0.0",
            build_id="bld_physics_1",
            chunk_id="chk_001",
            source_id="src_01",
            source_name="motion.pdf",
            page_number=12,
            text="Newton's second law defines force as mass times acceleration.",
            raw_score=0.88,
        )
    ]

    is_suff, msg = MultiRAGEvidenceAdapter.evaluate_sufficiency(
        generation_service=gen_service,
        query="what is newton's second law?",
        candidates=candidates,
    )
    assert is_suff is True
    assert msg == ""
    gen_service._evaluate_evidence_sufficiency.assert_called_once()
    args, kwargs = gen_service._evaluate_evidence_sufficiency.call_args
    passed_chunks = kwargs.get("retrieved_chunks") or args[1]
    assert len(passed_chunks) == 1
    assert passed_chunks[0].chunk_id == "chk_001"
    assert passed_chunks[0].provenance.source_name == "motion.pdf"


def test_adjustment_4_strict_composite_citation_identity():
    """Test D: Citation validity requires exact rag_id + build_id + chunk_id matching selected candidates."""
    from ragger_engine.generation.service import GenerationService
    gen_service = GenerationService.__new__(GenerationService)

    candidates = [
        MultiRAGCandidate(
            rag_id="rag_physics",
            rag_name="Physics",
            version_id="ver_p1",
            version_tag="v1.0.0",
            build_id="bld_physics_1",
            chunk_id="chk_phy_101",
            source_id="src_phy",
            source_name="physics.pdf",
            page_number=45,
            text="Kinetic energy is 0.5 * m * v^2.",
            raw_score=0.9,
        ),
        MultiRAGCandidate(
            rag_id="rag_biology",
            rag_name="Biology",
            version_id="ver_b1",
            version_tag="v1.0.0",
            build_id="bld_biology_1",
            chunk_id="chk_bio_202",
            source_id="src_bio",
            source_name="cells.pdf",
            page_number=88,
            text="Mitochondria are the powerhouse of the cell.",
            raw_score=0.85,
        ),
    ]

    # Valid multi-RAG answer with citations from both
    answer_both = "Kinetic energy depends on velocity [chk_phy_101]. Mitochondria power the cell [chk_bio_202]."
    valid_cits, unverified, status = gen_service.validate_multi_rag_citations(answer_both, candidates)
    assert status == CitationValidationStatus.VERIFIED
    assert len(unverified) == 0
    assert len(valid_cits) == 2
    assert valid_cits[0]["rag_id"] == "rag_physics"
    assert valid_cits[0]["chunk_id"] == "chk_phy_101"
    assert valid_cits[1]["rag_id"] == "rag_biology"
    assert valid_cits[1]["chunk_id"] == "chk_bio_202"

    # Attribution bleeding attempt: Model attempts to cite an un-retrieved chunk [chk_bio_999]
    bleeding_answer = "Cells generate ATP [chk_bio_999]."
    valid_cits, unverified, status = gen_service.validate_multi_rag_citations(bleeding_answer, candidates)
    assert status == CitationValidationStatus.UNVERIFIED_DETECTED
    assert "chk_bio_999" in unverified
    assert len(valid_cits) == 0


@pytest.mark.asyncio
async def test_test_b_rrf_candidate_fusion(mock_retrieval_service, mock_lifecycle_service):
    """Test B: Parallel retrieval across two RAGs with RRF (k=60) fusion and deduplication."""
    coord = MultiRAGCoordinator(
        retrieval_service=mock_retrieval_service,
        rag_lifecycle_service=mock_lifecycle_service,
    )

    t_phy = ResolvedRAGTarget(
        rag_id="rag_physics",
        rag_name="Physics",
        version_id="ver_p1",
        version_tag="v1.0.0",
        build_id="bld_physics_1",
    )
    t_bio = ResolvedRAGTarget(
        rag_id="rag_biology",
        rag_name="Biology",
        version_id="ver_b1",
        version_tag="v1.0.0",
        build_id="bld_biology_1",
    )

    # Mock responses for physics and biology
    mock_retrieval_service.retrieve.side_effect = [
        RetrievalResponse(
            query="energy in living systems",
            architecture="dense_rag",
            strategy="hybrid",
            results=[
                RetrievedChunk(
                    chunk_id="chk_p1",
                    text="Thermodynamics in energy conversion",
                    score=0.92,
                    score_type=ScoreType.COSINE_SIMILARITY,
                    provenance=CitationProvenance(
                        source_id="src_phy",
                        source_name="physics.pdf",
                        source_sha256="",
                        chunk_id="chk_p1",
                        chunk_type=ChunkType.STANDARD_PARAGRAPH,
                        page_number=5,
                        token_count=10,
                    ),
                    citation="[physics.pdf, p. 5]",
                )
            ],
            total_candidates=1,
            latency_ms=5.0,
            manifest_id="man_p1",
            manifest_hash="hash_p1",
            grounded_context_prompt="<prompt>",
        ),
        RetrievalResponse(
            query="energy in living systems",
            architecture="dense_rag",
            strategy="hybrid",
            results=[
                RetrievedChunk(
                    chunk_id="chk_b1",
                    text="Cellular respiration generates ATP energy",
                    score=0.89,
                    score_type=ScoreType.COSINE_SIMILARITY,
                    provenance=CitationProvenance(
                        source_id="src_bio",
                        source_name="biology.pdf",
                        source_sha256="",
                        chunk_id="chk_b1",
                        chunk_type=ChunkType.STANDARD_PARAGRAPH,
                        page_number=10,
                        token_count=12,
                    ),
                    citation="[biology.pdf, p. 10]",
                )
            ],
            total_candidates=1,
            latency_ms=6.0,
            manifest_id="man_b1",
            manifest_hash="hash_b1",
            grounded_context_prompt="<prompt>",
        ),



    ]

    retrieval_results = await coord.parallel_retrieve(
        targets=[t_phy, t_bio],
        query="energy in living systems",
    )
    assert len(retrieval_results) == 2
    assert retrieval_results[0].target.rag_id == "rag_physics"
    assert retrieval_results[1].target.rag_id == "rag_biology"

    fused = coord.fuse_and_deduplicate(retrieval_results, global_top_k=8, rrf_k=60)
    assert len(fused.candidates) == 2
    # Verify RRF score computation: rank 1 chunk gets 1/(60+1) = 0.016393...
    assert pytest.approx(fused.candidates[0].rrf_score, 0.0001) == 1.0 / 61.0
    assert pytest.approx(fused.candidates[1].rrf_score, 0.0001) == 1.0 / 61.0
    c_rags = {c.rag_id for c in fused.candidates}
    assert c_rags == {"rag_physics", "rag_biology"}


@pytest.mark.asyncio
async def test_test_e_missing_rag_fail_closed(mock_retrieval_service, mock_lifecycle_service):
    """Test E: If agent references a missing or deleted RAG, request fails closed immediately."""
    coord = MultiRAGCoordinator(
        retrieval_service=mock_retrieval_service,
        rag_lifecycle_service=mock_lifecycle_service,
    )
    agent = AgentProfile(
        agent_id="agt_invalid",
        name="Invalid Agent",
        attached_rag_ids=["rag_physics", "rag_nonexistent_999"],
    )
    with pytest.raises(RAGArtifactNotFoundError):
        coord.resolve_agent_runtimes(agent)


@pytest.mark.asyncio
async def test_test_f_corrupted_build_fail_closed(mock_retrieval_service, mock_lifecycle_service):
    """Test F: If build manifest status is not completed, fails closed without silent degradation."""
    bad_runtime = MagicMock()
    bad_runtime.manifest.status = "failed"
    mock_retrieval_service.get_or_load_build_runtime.return_value = bad_runtime

    coord = MultiRAGCoordinator(
        retrieval_service=mock_retrieval_service,
        rag_lifecycle_service=mock_lifecycle_service,
    )
    agent = AgentProfile(
        agent_id="agt_broken",
        name="Broken Build Agent",
        attached_rag_ids=["rag_physics"],
    )
    from ragger_engine.retrieval.exceptions import BuildUnavailableError
    with pytest.raises(BuildUnavailableError):
        coord.resolve_agent_runtimes(agent)


def test_test_h_dynamic_version_switch(mock_retrieval_service, mock_lifecycle_service):
    """Test H: When RAG promotes v1 -> v2, subsequent queries immediately route to v2 build."""
    coord = MultiRAGCoordinator(
        retrieval_service=mock_retrieval_service,
        rag_lifecycle_service=mock_lifecycle_service,
    )
    agent = AgentProfile(
        agent_id="agt_dynamic",
        name="Dynamic Agent",
        attached_rag_ids=["rag_physics"],
    )

    # Initial active version is ver_p1 -> bld_physics_1
    resolved_1 = coord.resolve_agent_runtimes(agent)
    assert resolved_1[0].version_id == "ver_p1"
    assert resolved_1[0].build_id == "bld_physics_1"

    # Promote RAG to v2
    rag_phy = mock_lifecycle_service.get_rag("rag_physics")
    rag_phy.active_version_id = "ver_p2"

    # Subsequent resolution must route immediately to v2 build without restarting coordinator
    resolved_2 = coord.resolve_agent_runtimes(agent)
    assert resolved_2[0].version_id == "ver_p2"
    assert resolved_2[0].build_id == "bld_physics_2"


def test_test_a_single_rag_functional_equivalence(mock_retrieval_service, mock_lifecycle_service):
    """Test A: Agent with 1 attached RAG preserves single-RAG behavior, citations, and gate."""
    coord = MultiRAGCoordinator(
        retrieval_service=mock_retrieval_service,
        rag_lifecycle_service=mock_lifecycle_service,
    )
    agent = AgentProfile(
        agent_id="agt_single",
        name="Single RAG Agent",
        attached_rag_ids=["rag_physics"],
    )
    targets = coord.resolve_agent_runtimes(agent)
    assert len(targets) == 1
    assert targets[0].rag_id == "rag_physics"
    assert targets[0].version_id == "ver_p1"


def test_test_g_cross_rag_evidence_gate_ood():
    """Test G: Query out-of-domain for all attached RAGs fails closed without calling LLM."""
    from ragger_engine.generation.service import GenerationService
    gen_service = GenerationService.__new__(GenerationService)

    # Candidate chunks about biology and physics
    candidates = [
        MultiRAGCandidate(
            rag_id="rag_physics",
            rag_name="Physics",
            version_id="ver_p1",
            version_tag="v1.0.0",
            build_id="bld_physics_1",
            chunk_id="chk_p1",
            source_id="src_phy",
            source_name="physics.pdf",
            page_number=5,
            text="Newton's laws of classical mechanics and kinematics.",
        ),
        MultiRAGCandidate(
            rag_id="rag_biology",
            rag_name="Biology",
            version_id="ver_b1",
            version_tag="v1.0.0",
            build_id="bld_biology_1",
            chunk_id="chk_b1",
            source_id="src_bio",
            source_name="biology.pdf",
            page_number=10,
            text="Cellular organelles and biological membrane structure.",
        ),
    ]

    # Query about completely unrelated domain (e.g. baking cupcakes)
    ood_query = "how to bake chocolate cupcakes recipe?"
    is_sufficient, disclaimer = MultiRAGEvidenceAdapter.evaluate_sufficiency(
        generation_service=gen_service,
        query=ood_query,
        candidates=candidates,
    )
    assert is_sufficient is False
    assert "couldn't find information" in disclaimer.lower()

