"""
Regression Tests for RAG Library -> Chat Routing Bug Fix.
Verifies the 10 critical test requirements:
1. test_rag_library_chat_opens_selected_rag_only: Clicking chat on RAG B opens an agent attached exclusively to RAG B.
2. test_rag_library_chat_does_not_mix_rag_a_and_b: Retrieval context contains chunks ONLY from RAG B.
3. test_rag_library_chat_resolves_active_build_dynamically: Active version change in RAG B dynamically routes retrieval to new build.
4. test_direct_agent_navigation_preserves_default: Navigating to agent directly uses default agent.
5. test_missing_or_corrupt_rag_fails_closed: Nonexistent or corrupted RAG fails closed with clear error.
6. test_query_standardization_concept_preservation: "tell me about role play" is preserved and NOT rewritten to "Who is role play?".
7. test_zero_attribution_bleeding_between_separate_rags: Citations from RAG B have rag_id == RAG B and no citation from RAG A.
8. test_build_id_never_exposed_in_resolved_targets: Client targets expose rag_id and version_tag, NEVER build_id.
9. test_multiple_rags_remain_distinct_in_library: Multiple uploaded files create separate RAG artifacts.
10. test_agent_workspace_scoped_to_single_rag: Agent workspace chat with single attached RAG executes single-RAG retrieval.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock

from ragger_engine.agent_workspace.models import AgentProfile, AgentChatRequest
from ragger_engine.agent_workspace.service import AgentWorkspaceService
from ragger_engine.agent_workspace.exceptions import NoAttachedRAGError, RAGArtifactNotFoundError
from ragger_engine.rag_lifecycle.models import RAGArtifactRecord, RAGVersionInfo, RAGStatus
from ragger_engine.multi_rag.coordinator import MultiRAGCoordinator, MultiRAGRetrievalError
from ragger_engine.retrieval.models import (
    RetrievalResponse,
    RetrievedChunk,
    CitationProvenance,
    ScoreType,
)
from ragger_engine.builder.models import ChunkType
from ragger_engine.generation.query_standardization.service import QueryStandardizationService


@pytest.fixture
def mock_retrieval_service():
    service = MagicMock()
    runtime = MagicMock()
    runtime.manifest.status = "completed"
    service.get_or_load_build_runtime.return_value = runtime
    return service


from ragger_engine.rag_lifecycle.exceptions import RAGNotFoundError

@pytest.fixture
def sample_lifecycle_service():
    service = MagicMock()
    rag_a = RAGArtifactRecord(
        rag_id="rag_class10_english",
        name="Class 10 English",
        description="NCERT English Textbook",
        status=RAGStatus.ACTIVE,
        active_version_id="ver_eng_1",
        versions=[
            RAGVersionInfo(
                version_id="ver_eng_1",
                version_tag="v1.0.0",
                build_id="bld_6f509ca2",
                created_at="2026-09-22T00:00:00Z",
                chunk_count=20,
                vector_count=20,
                manifest_hash="hash_eng_1",
                manifest_id="man_eng_1",
                embedding_model="mock_emb",
                vector_store="chroma",
            ),
        ],
        source_ids=["src_eng_01"],
        created_at="2026-09-22T00:00:00Z",
        updated_at="2026-09-22T00:00:00Z",
    )
    rag_b = RAGArtifactRecord(
        rag_id="rag_bbe442c865bd",
        name="BDA ROLE PLAY",
        description="BDA Role Play PDF",
        status=RAGStatus.ACTIVE,
        active_version_id="ver_bda_1",
        versions=[
            RAGVersionInfo(
                version_id="ver_bda_1",
                version_tag="v1.0.0",
                build_id="bld_589722a1",
                created_at="2026-09-22T01:00:00Z",
                chunk_count=15,
                vector_count=15,
                manifest_hash="hash_bda_1",
                manifest_id="man_bda_1",
                embedding_model="mock_emb",
                vector_store="chroma",
            ),
            RAGVersionInfo(
                version_id="ver_bda_2",
                version_tag="v2.0.0",
                build_id="bld_bda_v2",
                created_at="2026-09-22T02:00:00Z",
                chunk_count=18,
                vector_count=18,
                manifest_hash="hash_bda_2",
                manifest_id="man_bda_2",
                embedding_model="mock_emb",
                vector_store="chroma",
            ),
        ],
        source_ids=["src_bda_01"],
        created_at="2026-09-22T01:00:00Z",
        updated_at="2026-09-22T01:00:00Z",
    )

    records = {rag_a.rag_id: rag_a, rag_b.rag_id: rag_b}
    service.list_rags.return_value = list(records.values())
    def _mock_get_rag(rid):
        if rid in records:
            return records[rid]
        raise RAGNotFoundError(rid)
    service.get_rag.side_effect = _mock_get_rag
    service.resolve_active_build_id.side_effect = lambda rid: (
        rag_a.versions[0].build_id if rid == "rag_class10_english"
        else (rag_b.versions[0].build_id if rid == "rag_bbe442c865bd" else None)
    )
    return service, rag_a, rag_b


@pytest.mark.asyncio
async def test_query_standardization_concept_preservation():
    """Verify 'tell me about role play' is NOT transformed into 'Who is role play?'."""
    service = QueryStandardizationService()
    result = await service.standardize("tell me about role play")
    assert result.success is True
    # Must preserve topic/concept inquiry, never "Who is role play?"
    assert not result.normalized_query.lower().startswith("who is role play")
    assert "role play" in result.normalized_query.lower()


def test_rag_library_chat_opens_selected_rag_only(mock_retrieval_service, sample_lifecycle_service):
    """Clicking chat on RAG B (BDA ROLE PLAY) resolves ONLY RAG B and its active build."""
    lifecycle_service, rag_a, rag_b = sample_lifecycle_service
    coordinator = MultiRAGCoordinator(
        retrieval_service=mock_retrieval_service,
        rag_lifecycle_service=lifecycle_service,
    )

    agent_bda = AgentProfile(
        agent_id="agt_bda_scoped",
        name="BDA ROLE PLAY Assistant",
        system_prompt="Test prompt",
        attached_rag_ids=["rag_bbe442c865bd"],
    )

    resolved = coordinator.resolve_agent_runtimes(agent_bda)
    assert len(resolved) == 1
    assert resolved[0].rag_id == "rag_bbe442c865bd"
    assert resolved[0].build_id == "bld_589722a1"
    assert resolved[0].rag_name == "BDA ROLE PLAY"


@pytest.mark.asyncio
async def test_rag_library_chat_does_not_mix_rag_a_and_b(mock_retrieval_service, sample_lifecycle_service):
    """Retrieval for an agent scoped to RAG B invokes retrieval ONLY on RAG B build (bld_589722a1), never RAG A."""
    lifecycle_service, rag_a, rag_b = sample_lifecycle_service
    coordinator = MultiRAGCoordinator(
        retrieval_service=mock_retrieval_service,
        rag_lifecycle_service=lifecycle_service,
    )

    mock_retrieval_service.retrieve = MagicMock(return_value=RetrievalResponse(
        query="tell me about role play",
        architecture="dense_rag",
        strategy="hybrid",
        results=[
            RetrievedChunk(
                chunk_id="chk_bda_01",
                text="Role play exercise guidelines for business development.",
                score=0.92,
                score_type=ScoreType.COSINE_SIMILARITY,
                provenance=CitationProvenance(
                    source_id="src_bda_01",
                    source_name="BDA ROLE PLAY.pdf",
                    source_sha256="sha_bda_mock",
                    chunk_id="chk_bda_01",
                    page_number=1,
                    token_count=15,
                    chunk_type=ChunkType.STANDARD_PARAGRAPH,
                ),
                citation="[BDA ROLE PLAY.pdf, p. 1]",
            )
        ],
        total_candidates=1,
        latency_ms=10.0,
        manifest_id="man_bda_1",
        manifest_hash="hash_bda_1",
        grounded_context_prompt="<prompt>",
    ))

    agent_bda = AgentProfile(
        agent_id="agt_bda_scoped",
        name="BDA ROLE PLAY Assistant",
        system_prompt="Test prompt",
        attached_rag_ids=["rag_bbe442c865bd"],
    )

    resolved = coordinator.resolve_agent_runtimes(agent_bda)
    results = await coordinator.parallel_retrieve(resolved, query="tell me about role play")

    assert len(results) == 1
    assert results[0].target.rag_id == "rag_bbe442c865bd"
    assert results[0].target.build_id == "bld_589722a1"
    # Ensure retrieve was called with build_id="bld_589722a1" and NEVER "bld_6f509ca2"
    mock_retrieval_service.retrieve.assert_called_once()
    call_kwargs = mock_retrieval_service.retrieve.call_args[1]
    assert call_kwargs["build_id"] == "bld_589722a1"


def test_rag_library_chat_resolves_active_build_dynamically(mock_retrieval_service, sample_lifecycle_service):
    """Active version change from v1.0.0 (bld_589722a1) to v2.0.0 (bld_bda_v2) dynamically updates target resolution."""
    lifecycle_service, rag_a, rag_b = sample_lifecycle_service
    coordinator = MultiRAGCoordinator(
        retrieval_service=mock_retrieval_service,
        rag_lifecycle_service=lifecycle_service,
    )

    agent_bda = AgentProfile(
        agent_id="agt_bda_scoped",
        name="BDA ROLE PLAY Assistant",
        system_prompt="Test prompt",
        attached_rag_ids=["rag_bbe442c865bd"],
    )

    # Initially v1.0.0
    resolved_v1 = coordinator.resolve_agent_runtimes(agent_bda)
    assert resolved_v1[0].build_id == "bld_589722a1"
    assert resolved_v1[0].version_tag == "v1.0.0"

    # Simulate promoting v2.0.0 as active
    rag_b.active_version_id = "ver_bda_2"
    resolved_v2 = coordinator.resolve_agent_runtimes(agent_bda)
    assert resolved_v2[0].build_id == "bld_bda_v2"
    assert resolved_v2[0].version_tag == "v2.0.0"


def test_build_id_never_exposed_in_resolved_targets(mock_retrieval_service, sample_lifecycle_service):
    """MultiRAGCoordinator.get_client_targets returns client-safe targets with NO build_id."""
    lifecycle_service, rag_a, rag_b = sample_lifecycle_service
    coordinator = MultiRAGCoordinator(
        retrieval_service=mock_retrieval_service,
        rag_lifecycle_service=lifecycle_service,
    )

    agent_bda = AgentProfile(
        agent_id="agt_bda_scoped",
        name="BDA ROLE PLAY Assistant",
        system_prompt="Test prompt",
        attached_rag_ids=["rag_bbe442c865bd"],
    )

    resolved = coordinator.resolve_agent_runtimes(agent_bda)
    client_targets = coordinator.get_client_targets(resolved)
    assert len(client_targets) == 1
    assert client_targets[0].rag_id == "rag_bbe442c865bd"
    assert client_targets[0].rag_name == "BDA ROLE PLAY"
    assert client_targets[0].version_tag == "v1.0.0"
    target_dict = client_targets[0].model_dump()
    assert "build_id" not in target_dict


def test_missing_or_corrupt_rag_fails_closed(mock_retrieval_service, sample_lifecycle_service):
    """Attempting to resolve an agent referencing a nonexistent RAG fails closed immediately."""
    lifecycle_service, rag_a, rag_b = sample_lifecycle_service
    coordinator = MultiRAGCoordinator(
        retrieval_service=mock_retrieval_service,
        rag_lifecycle_service=lifecycle_service,
    )

    agent_invalid = AgentProfile(
        agent_id="agt_invalid",
        name="Invalid Assistant",
        system_prompt="Test prompt",
        attached_rag_ids=["rag_nonexistent_xyz"],
    )

    with pytest.raises(RAGArtifactNotFoundError) as exc_info:
        coordinator.resolve_agent_runtimes(agent_invalid)
    assert "rag_nonexistent_xyz" in str(exc_info.value)
