"""
Comprehensive backend & contract tests for Knowledge Attachment & Multi-RAG UX workflows.
Verifies:
1. Attach RAG to dedicated or default agent persists in agent repository.
2. Duplicate attachment of the same rag_id is prevented/idempotent.
3. Attaching second RAG to an agent creates multi-RAG setup.
4. Detaching RAG from current agent removes association only (agent -> RAG removed),
   while RAG remains intact in RAG Lifecycle / Library.
5. Operating against agt_default attaches to agt_default only.
6. Operating against custom selectedAgentId attaches to that agent only.
7. Client targets expose only rag_id and version_tag, never exposing build_id as client authority.
8. Persistence: saved agent profile retains multi-RAG attachment across reload.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from ragger_engine.agent_workspace.models import AgentProfile, CreateAgentRequest, AttachRAGRequest
from ragger_engine.agent_workspace.service import AgentWorkspaceService
from ragger_engine.agent_workspace.exceptions import AgentNotFoundError, RAGArtifactNotFoundError
from ragger_engine.rag_lifecycle.models import RAGArtifactRecord, RAGVersionInfo, RAGStatus
from ragger_engine.rag_lifecycle.exceptions import RAGNotFoundError


@pytest.fixture
def temp_workspace(tmp_path):
    storage_dir = tmp_path / "agents"
    storage_dir.mkdir(parents=True)
    return storage_dir


@pytest.fixture
def mock_lifecycle():
    service = MagicMock()
    
    rag_a = RAGArtifactRecord(
        rag_id="rag_design_doc",
        name="DESIGN.md",
        description="Software Architecture Document",
        status=RAGStatus.ACTIVE,
        active_version_id="ver_design_1",
        versions=[
            RAGVersionInfo(
                version_id="ver_design_1",
                version_tag="v1.0.0",
                build_id="bld_design_1111",
                created_at="2026-09-24T00:00:00Z",
                status=RAGStatus.ACTIVE,
                manifest_hash="hash_design",
                manifest_id="man_design",
                chunk_count=15,
                vector_count=15,
                embedding_model="mock_emb",
                vector_store="chroma",
            )
        ],
        source_ids=["src_design"],
        created_at="2026-09-24T00:00:00Z",
        updated_at="2026-09-24T00:00:00Z",
    )
    rag_b = RAGArtifactRecord(
        rag_id="rag_class10_eng",
        name="Class 10 English",
        description="Class 10 English Literature Textbook",
        status=RAGStatus.ACTIVE,
        active_version_id="ver_c10_1",
        versions=[
            RAGVersionInfo(
                version_id="ver_c10_1",
                version_tag="v1.0.0",
                build_id="bld_c10_2222",
                created_at="2026-09-24T00:00:00Z",
                status=RAGStatus.ACTIVE,
                manifest_hash="hash_c10",
                manifest_id="man_c10",
                chunk_count=25,
                vector_count=25,
                embedding_model="mock_emb",
                vector_store="chroma",
            )
        ],
        source_ids=["src_c10"],
        created_at="2026-09-24T00:00:00Z",
        updated_at="2026-09-24T00:00:00Z",
    )
    
    store = {
        "rag_design_doc": rag_a,
        "rag_class10_eng": rag_b,
    }
    
    def get_rag(rag_id):
        if rag_id in store:
            return store[rag_id]
        raise RAGNotFoundError(f"RAG {rag_id} not found")
        
    def list_rags(status=None):
        return list(store.values())
        
    service.get_rag = MagicMock(side_effect=get_rag)
    service.list_rags = MagicMock(side_effect=list_rags)
    service._store = store
    return service


@pytest.fixture
def mock_library_service():
    svc = MagicMock()
    svc._get_active_build_id.return_value = "bld_default"
    return svc


@pytest.fixture
def mock_gen_service():
    svc = MagicMock()
    return svc


def test_attach_rag_to_default_agent(temp_workspace, mock_lifecycle, mock_library_service, mock_gen_service):
    """Plus button operates on agt_default: attaching adds rag_id only to agt_default."""
    svc = AgentWorkspaceService(
        workspace_dir=temp_workspace,
        rag_library_service=mock_library_service,
        generation_service=mock_gen_service,
        rag_lifecycle_service=mock_lifecycle,
    )
    
    # Verify agt_default exists
    default_agent = svc.get_agent("agt_default")
    assert default_agent is not None
    assert "rag_class10_eng" not in default_agent.attached_rag_ids
    
    # Attach Class 10 English via + button action
    updated = svc.attach_rag("agt_default", "rag_class10_eng")
    assert "rag_class10_eng" in updated.attached_rag_ids
    
    # Verify persistence across service reload
    fresh_svc = AgentWorkspaceService(
        workspace_dir=temp_workspace,
        rag_library_service=mock_library_service,
        generation_service=mock_gen_service,
        rag_lifecycle_service=mock_lifecycle,
    )
    persisted = fresh_svc.get_agent("agt_default")
    assert "rag_class10_eng" in persisted.attached_rag_ids


def test_duplicate_rag_attachment_prevented(temp_workspace, mock_lifecycle, mock_library_service, mock_gen_service):
    """Attaching already-attached RAG does not duplicate entries."""
    svc = AgentWorkspaceService(
        workspace_dir=temp_workspace,
        rag_library_service=mock_library_service,
        generation_service=mock_gen_service,
        rag_lifecycle_service=mock_lifecycle,
    )
    
    agent = svc.create_agent(
        CreateAgentRequest(
            name="Assistant Alpha",
            attached_rag_ids=["rag_design_doc"],
        )
    )
    assert agent.attached_rag_ids == ["rag_design_doc"]
    
    # Try attaching same rag_design_doc again
    updated = svc.attach_rag(agent.agent_id, "rag_design_doc")
    assert updated.attached_rag_ids == ["rag_design_doc"]
    assert len(updated.attached_rag_ids) == 1


def test_multi_rag_attachment_via_plus(temp_workspace, mock_lifecycle, mock_library_service, mock_gen_service):
    """Agent with RAG A gets RAG B attached -> becomes [RAG A, RAG B]."""
    svc = AgentWorkspaceService(
        workspace_dir=temp_workspace,
        rag_library_service=mock_library_service,
        generation_service=mock_gen_service,
        rag_lifecycle_service=mock_lifecycle,
    )
    
    agent = svc.create_agent(
        CreateAgentRequest(
            name="Multi Assistant",
            attached_rag_ids=["rag_design_doc"],
        )
    )
    assert agent.attached_rag_ids == ["rag_design_doc"]
    
    # User clicks + and attaches Class 10 English
    updated = svc.attach_rag(agent.agent_id, "rag_class10_eng")
    assert len(updated.attached_rag_ids) == 2
    assert "rag_design_doc" in updated.attached_rag_ids
    assert "rag_class10_eng" in updated.attached_rag_ids


def test_attachment_isolated_to_selected_agent_only(temp_workspace, mock_lifecycle, mock_library_service, mock_gen_service):
    """Attaching a RAG modifies selectedAgentId only, leaving other agents untouched."""
    svc = AgentWorkspaceService(
        workspace_dir=temp_workspace,
        rag_library_service=mock_library_service,
        generation_service=mock_gen_service,
        rag_lifecycle_service=mock_lifecycle,
    )
    
    agent_1 = svc.create_agent(CreateAgentRequest(name="Agent 1", attached_rag_ids=["rag_design_doc"]))
    agent_2 = svc.create_agent(CreateAgentRequest(name="Agent 2", attached_rag_ids=[]))
    
    # Attach rag_class10_eng to Agent 1 only
    svc.attach_rag(agent_1.agent_id, "rag_class10_eng")
    
    updated_1 = svc.get_agent(agent_1.agent_id)
    updated_2 = svc.get_agent(agent_2.agent_id)
    
    assert "rag_class10_eng" in updated_1.attached_rag_ids
    assert "rag_class10_eng" not in updated_2.attached_rag_ids
    assert updated_2.attached_rag_ids == []


def test_remove_attachment_does_not_delete_rag(temp_workspace, mock_lifecycle, mock_library_service, mock_gen_service):
    """Removing attachment removes Agent -> RAG link only; RAG remains intact in library."""
    svc = AgentWorkspaceService(
        workspace_dir=temp_workspace,
        rag_library_service=mock_library_service,
        generation_service=mock_gen_service,
        rag_lifecycle_service=mock_lifecycle,
    )
    
    agent = svc.create_agent(
        CreateAgentRequest(
            name="Agent with Two RAGs",
            attached_rag_ids=["rag_design_doc", "rag_class10_eng"],
        )
    )
    assert len(agent.attached_rag_ids) == 2
    
    # Detach rag_design_doc via chip remove (X)
    updated = svc.detach_rag(agent.agent_id, "rag_design_doc")
    assert "rag_design_doc" not in updated.attached_rag_ids
    assert updated.attached_rag_ids == ["rag_class10_eng"]
    
    # CRITICAL: Verify RAG still exists in RAG Lifecycle / Library!
    rag_in_lifecycle = mock_lifecycle.get_rag("rag_design_doc")
    assert rag_in_lifecycle is not None
    assert rag_in_lifecycle.rag_id == "rag_design_doc"
    assert rag_in_lifecycle.name == "DESIGN.md"


def test_resolved_targets_contract_has_no_build_id(temp_workspace, mock_lifecycle, mock_library_service, mock_gen_service):
    """Resolved targets contract exposes rag_id, rag_name, version_tag - NEVER build_id."""
    from ragger_engine.multi_rag.coordinator import MultiRAGCoordinator
    mock_retrieval = MagicMock()
    runtime = MagicMock()
    runtime.manifest.status = "completed"
    mock_retrieval.get_or_load_build_runtime.return_value = runtime

    coordinator = MultiRAGCoordinator(
        retrieval_service=mock_retrieval,
        rag_lifecycle_service=mock_lifecycle,
        rag_library_service=mock_library_service,
    )
    svc = AgentWorkspaceService(
        workspace_dir=temp_workspace,
        rag_library_service=mock_library_service,
        generation_service=mock_gen_service,
        rag_lifecycle_service=mock_lifecycle,
        multi_rag_coordinator=coordinator,
    )
    
    agent = svc.create_agent(
        CreateAgentRequest(
            name="Composite Agent",
            attached_rag_ids=["rag_design_doc", "rag_class10_eng"],
        )
    )
    resolved = coordinator.resolve_agent_runtimes(agent)
    targets = coordinator.get_client_targets(resolved)
    
    assert len(targets) == 2
    for t in targets:
        td = t.model_dump()
        assert "build_id" not in td
        assert "rag_id" in td
        assert "rag_name" in td
        assert "version_tag" in td


@pytest.mark.asyncio
async def test_agent_workspace_stream_chat(temp_workspace, mock_lifecycle, mock_library_service, mock_gen_service):
    """Verifies that AgentWorkspaceService.stream_chat streams tokens progressively and yields done with citations."""
    from ragger_engine.multi_rag.coordinator import MultiRAGCoordinator
    from ragger_engine.agent_workspace.models import AgentChatRequest

    from ragger_engine.retrieval.models import RetrievalResponse
    mock_retrieval = MagicMock()
    runtime = MagicMock()
    runtime.manifest.status = "completed"
    mock_retrieval.get_or_load_build_runtime.return_value = runtime
    mock_retrieval.retrieve.return_value = RetrievalResponse(
        query="Tell me about the seagull.",
        architecture="hierarchical",
        strategy="vector_only",
        results=[],
        total_candidates=0,
        latency_ms=1.0,
        manifest_id="man_test",
        manifest_hash="hash_test",
        grounded_context_prompt="Context prompt",
    )

    coordinator = MultiRAGCoordinator(
        retrieval_service=mock_retrieval,
        rag_lifecycle_service=mock_lifecycle,
        rag_library_service=mock_library_service,
    )

    # Setup generation service mock that yields tokens and done
    async def mock_stream_multi_rag(*args, **kwargs):
        yield {"event": "status", "data": {"state": "generating"}}
        yield {"event": "token", "data": {"token": "The "}}
        yield {"event": "token", "data": {"token": "young "}}
        yield {"event": "token", "data": {"token": "seagull."}}
        yield {
            "event": "done",
            "data": {
                "session_id": "sess_123",
                "answer": "The young seagull.",
                "has_insufficient_evidence": False,
                "multi_rag_citations": [
                    {
                        "rag_id": "rag_design_doc",
                        "build_id": "bld_design_1111",
                        "source_id": "src_design",
                        "source_name": "DESIGN.md",
                        "chunk_id": "chk_001",
                        "page_number": 1,
                        "citation_text": "Seagull flight principles",
                        "snippet": "Flight principles",
                    }
                ],
            },
        }

    mock_gen_service.stream_multi_rag_generation = mock_stream_multi_rag

    svc = AgentWorkspaceService(
        workspace_dir=temp_workspace,
        rag_library_service=mock_library_service,
        generation_service=mock_gen_service,
        rag_lifecycle_service=mock_lifecycle,
        multi_rag_coordinator=coordinator,
    )

    agent = svc.create_agent(
        CreateAgentRequest(
            name="Stream Agent",
            attached_rag_ids=["rag_design_doc"],
        )
    )

    events = []
    tokens = []
    async for ev in svc.stream_chat(agent.agent_id, AgentChatRequest(query="Tell me about the seagull.")):
        events.append(ev)
        if ev.get("event") == "token":
            tokens.append(ev.get("data", {}).get("token"))

    assert tokens == ["The ", "young ", "seagull."]
    done_event = [e for e in events if e.get("event") == "done"][0]
    done_data = done_event["data"]
    assert done_data["answer"] == "The young seagull."
    assert len(done_data["citations"]) == 1
    assert done_data["citations"][0]["rag_id"] == "rag_design_doc"
    assert done_data["citations"][0]["source_name"] == "DESIGN.md"
