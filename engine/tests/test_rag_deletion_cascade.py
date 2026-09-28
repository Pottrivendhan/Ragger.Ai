"""
Tests for RAG Deletion Cascade and Stale Reference Cleanup.

Verifies:
1. TEST 1: Single-RAG dedicated agent is deleted when its only RAG is deleted.
2. TEST 2: Multi-RAG agent remains and has only the remaining RAG when one RAG is deleted.
3. TEST 3: agt_default is preserved even if all attached RAGs are detached/deleted.
4. TEST 4: list_agents() defensively reconciles stale 0-RAG dedicated agents and deleted RAGs.
5. TEST 5: Retrieval fails closed (NoAttachedRAGError or RAGNotFoundError) for deleted RAGs with NO Class 10 fallback.
6. TEST 6: Other unrelated RAGs and agents remain untouched when one RAG is deleted.
7. TEST 7: build_id is never used as deletion or client target authority.
"""

import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

from ragger_engine.agent_workspace.models import AgentProfile, AgentChatRequest
from ragger_engine.agent_workspace.service import AgentWorkspaceService
from ragger_engine.agent_workspace.exceptions import NoAttachedRAGError, RAGArtifactNotFoundError
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
        rag_id="rag_a_test",
        name="RAG A Test",
        description="Knowledge base A",
        status=RAGStatus.ACTIVE,
        active_version_id="ver_a_1",
        versions=[
            RAGVersionInfo(
                version_id="ver_a_1",
                version_tag="v1.0.0",
                build_id="bld_a_1111",
                created_at="2026-09-24T00:00:00Z",
                status=RAGStatus.ACTIVE,
                manifest_hash="hash_a",
                manifest_id="man_a",
                chunk_count=10,
                vector_count=10,
                embedding_model="mock_emb",
                vector_store="chroma",
            )
        ],
        source_ids=["src_a"],
        created_at="2026-09-24T00:00:00Z",
        updated_at="2026-09-24T00:00:00Z",
    )
    rag_b = RAGArtifactRecord(
        rag_id="rag_b_test",
        name="RAG B Test",
        description="Knowledge base B",
        status=RAGStatus.ACTIVE,
        active_version_id="ver_b_1",
        versions=[
            RAGVersionInfo(
                version_id="ver_b_1",
                version_tag="v1.0.0",
                build_id="bld_b_2222",
                created_at="2026-09-24T00:00:00Z",
                status=RAGStatus.ACTIVE,
                manifest_hash="hash_b",
                manifest_id="man_b",
                chunk_count=10,
                vector_count=10,
                embedding_model="mock_emb",
                vector_store="chroma",
            )
        ],
        source_ids=["src_b"],
        created_at="2026-09-24T00:00:00Z",
        updated_at="2026-09-24T00:00:00Z",
    )
    
    store = {
        "rag_a_test": rag_a,
        "rag_b_test": rag_b,
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


from ragger_engine.agent_workspace.models import AgentProfile, CreateAgentRequest, AgentChatRequest


def test_single_rag_dedicated_agent_deleted_on_rag_detach(temp_workspace, mock_lifecycle, mock_library_service, mock_gen_service):
    """TEST 1: If a dedicated agent has only RAG A, detaching RAG A deletes the agent."""
    svc = AgentWorkspaceService(
        workspace_dir=temp_workspace,
        rag_library_service=mock_library_service,
        generation_service=mock_gen_service,
        rag_lifecycle_service=mock_lifecycle,
    )
    
    # Create dedicated agent for rag_a_test
    agent_a = svc.create_agent(
        CreateAgentRequest(
            name="RAG A Dedicated Assistant",
            attached_rag_ids=["rag_a_test"],
        )
    )
    assert agent_a.agent_id in svc._load_agents_map()
    
    # Detach rag_a_test (simulating RAG A deletion cascade)
    affected = svc.detach_rag_from_all_agents("rag_a_test")
    assert agent_a.agent_id in affected
    
    # The dedicated agent should be completely removed from agents
    assert agent_a.agent_id not in svc._load_agents_map()
    
    # Verify persistence file
    agents_file = temp_workspace / "agents" / "agents.json"
    with open(agents_file, "r") as f:
        data = json.load(f)
    assert agent_a.agent_id not in data


def test_multi_rag_agent_removes_only_deleted_rag(temp_workspace, mock_lifecycle, mock_library_service, mock_gen_service):
    """TEST 2: If an agent has [RAG A, RAG B], detaching RAG A leaves RAG B attached."""
    svc = AgentWorkspaceService(
        workspace_dir=temp_workspace,
        rag_library_service=mock_library_service,
        generation_service=mock_gen_service,
        rag_lifecycle_service=mock_lifecycle,
    )
    
    # Create multi-RAG agent
    multi_agent = svc.create_agent(
        CreateAgentRequest(
            name="Research Assistant",
            attached_rag_ids=["rag_a_test", "rag_b_test"],
        )
    )
    assert multi_agent.agent_id in svc._load_agents_map()
    assert len(multi_agent.attached_rag_ids) == 2
    
    # Detach rag_a_test
    affected = svc.detach_rag_from_all_agents("rag_a_test")
    assert multi_agent.agent_id in affected
    
    # Multi-RAG agent remains valid with only rag_b_test
    updated = svc.get_agent(multi_agent.agent_id)
    assert updated is not None
    assert updated.attached_rag_ids == ["rag_b_test"]


def test_default_agent_preserved_even_when_empty(temp_workspace, mock_lifecycle, mock_library_service, mock_gen_service):
    """TEST 3 & 9: agt_default is preserved even if all attached RAGs are detached."""
    svc = AgentWorkspaceService(
        workspace_dir=temp_workspace,
        rag_library_service=mock_library_service,
        generation_service=mock_gen_service,
        rag_lifecycle_service=mock_lifecycle,
    )
    
    default_agent = svc.get_agent("agt_default")
    assert default_agent is not None
    
    # Attach rag_a_test to default agent
    svc.attach_rag("agt_default", "rag_a_test")
    assert "rag_a_test" in svc.get_agent("agt_default").attached_rag_ids
    
    # Detach rag_a_test
    svc.detach_rag_from_all_agents("rag_a_test")
    
    # agt_default MUST NOT be deleted
    refreshed_default = svc.get_agent("agt_default")
    assert refreshed_default is not None
    assert refreshed_default.agent_id == "agt_default"
    assert "rag_a_test" not in refreshed_default.attached_rag_ids


def test_list_agents_defensively_reconciles_stale_records(temp_workspace, mock_lifecycle, mock_library_service, mock_gen_service):
    """TEST 4 & 6: list_agents() removes dedicated agents whose RAG was deleted or has 0 RAGs."""
    svc = AgentWorkspaceService(
        workspace_dir=temp_workspace,
        rag_library_service=mock_library_service,
        generation_service=mock_gen_service,
        rag_lifecycle_service=mock_lifecycle,
    )
    
    # Create dedicated agent for rag_a_test
    agent_a = svc.create_agent(
        CreateAgentRequest(
            name="RAG A Assistant",
            attached_rag_ids=["rag_a_test"],
        )
    )
    
    # Directly corrupt/simulate stale state where rag_a_test is deleted from lifecycle
    del mock_lifecycle._store["rag_a_test"]
    
    # Calling list_agents() should detect that rag_a_test does not exist and purge agent_a
    active_agents = svc.list_agents()
    agent_ids = [a.agent_id for a in active_agents]
    
    assert agent_a.agent_id not in agent_ids
    assert "agt_default" in agent_ids


def test_deleted_rag_fails_closed_no_class10_fallback(temp_workspace, mock_lifecycle, mock_library_service, mock_gen_service):
    """TEST 5: Executing against a deleted RAG fails closed without falling back to Class 10."""
    from ragger_engine.multi_rag.coordinator import MultiRAGCoordinator
    coordinator = MultiRAGCoordinator(
        retrieval_service=MagicMock(),
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
    
    # Create agent attached to rag_a_test
    agent = svc.create_agent(
        CreateAgentRequest(
            name="Temporary Agent",
            attached_rag_ids=["rag_a_test"],
        )
    )
    
    # Delete rag_a_test from lifecycle
    del mock_lifecycle._store["rag_a_test"]
    
    # Attempting to resolve runtimes should fail closed (RAGArtifactNotFoundError)
    with pytest.raises(RAGArtifactNotFoundError) as exc:
        coordinator.resolve_agent_runtimes(agent)
    assert "rag_a_test" in str(exc.value)
    assert "Class 10" not in str(exc.value)


def test_build_id_never_used_as_authority_in_resolved_targets(temp_workspace, mock_lifecycle, mock_library_service, mock_gen_service):
    """TEST 8 & 10: Client targets expose rag_id and version_tag, never build_id as key authority."""
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
            name="B Assistant",
            attached_rag_ids=["rag_b_test"],
        )
    )
    resolved = coordinator.resolve_agent_runtimes(agent)
    targets = coordinator.get_client_targets(resolved)
    assert len(targets) == 1
    target = targets[0]
    
    assert target.rag_id == "rag_b_test"
    assert target.rag_name == "RAG B Test"
    assert target.version_tag == "v1.0.0"
    target_dict = target.model_dump()
    assert "build_id" not in target_dict


def test_agent_detach_rag_multi_and_empty_lifecycle(temp_workspace, mock_lifecycle, mock_library_service, mock_gen_service):
    """
    Tests 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 for AI Agent Workspace Detach / Remove knowledge:
    - Attach RAG_A, RAG_B, RAG_C
    - Remove RAG_B -> [RAG_A, RAG_C] remain
    - Remove RAG_A -> [RAG_C] remains
    - Remove final RAG -> 0 attached RAGs, agent preserved, no default fallback
    - RAG Library is NOT touched (artifacts still exist)
    - Re-attaching works
    - Resolved targets update accordingly without build_id
    """
    from ragger_engine.multi_rag.coordinator import MultiRAGCoordinator
    mock_retrieval = MagicMock()
    runtime = MagicMock()
    runtime.manifest.status = "completed"
    mock_retrieval.get_or_load_build_runtime.return_value = runtime

    # Add rag_c to mock lifecycle
    rag_c = RAGArtifactRecord(
        rag_id="rag_c_test",
        name="RAG C Test",
        description="Knowledge base C",
        status=RAGStatus.ACTIVE,
        active_version_id="ver_c_1",
        versions=[
            RAGVersionInfo(
                version_id="ver_c_1",
                version_tag="v1.0.0",
                build_id="bld_c_3333",
                created_at="2026-09-24T00:00:00Z",
                status=RAGStatus.ACTIVE,
                manifest_hash="hash_c",
                manifest_id="man_c",
                chunk_count=5,
                vector_count=5,
                embedding_model="mock_emb",
                vector_store="chroma",
            )
        ],
        source_ids=["src_c"],
        created_at="2026-09-24T00:00:00Z",
        updated_at="2026-09-24T00:00:00Z",
    )
    mock_lifecycle._store["rag_c_test"] = rag_c

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

    # 1. Attach RAG_A, RAG_B, RAG_C to an agent
    agent = svc.create_agent(
        CreateAgentRequest(
            name="Multi RAG Agent",
            attached_rag_ids=["rag_a_test", "rag_b_test", "rag_c_test"],
        )
    )
    assert agent.attached_rag_ids == ["rag_a_test", "rag_b_test", "rag_c_test"]

    # Also create Agent B with RAG_A and RAG_B to verify Agent B is unaffected
    agent_b = svc.create_agent(
        CreateAgentRequest(
            name="Agent B",
            attached_rag_ids=["rag_a_test", "rag_b_test"],
        )
    )

    # TEST 1: Remove RAG_B from agent
    updated = svc.detach_rag(agent.agent_id, "rag_b_test")
    assert updated.attached_rag_ids == ["rag_a_test", "rag_c_test"]

    # TEST 5: Verify Agent B remains unaffected
    agent_b_loaded = svc.get_agent(agent_b.agent_id)
    assert agent_b_loaded.attached_rag_ids == ["rag_a_test", "rag_b_test"]

    # TEST 4: Verify RAG_B still exists in RAG Library / lifecycle store
    assert "rag_b_test" in mock_lifecycle._store

    # TEST 8: Resolved targets must now only contain rag_a_test and rag_c_test
    resolved = coordinator.resolve_agent_runtimes(updated)
    client_targets = coordinator.get_client_targets(resolved)
    target_ids = [t.rag_id for t in client_targets]
    assert "rag_b_test" not in target_ids
    assert target_ids == ["rag_a_test", "rag_c_test"]

    # TEST 7: Client targets never contain build_id
    for t in client_targets:
        assert "build_id" not in t.model_dump()

    # TEST 2: Remove RAG_A
    updated = svc.detach_rag(agent.agent_id, "rag_a_test")
    assert updated.attached_rag_ids == ["rag_c_test"]

    # TEST 3: Remove final RAG (RAG_C)
    updated = svc.detach_rag(agent.agent_id, "rag_c_test")
    assert updated.attached_rag_ids == []

    # Verify empty agent is retained without falling back to Class 10
    reloaded = svc.get_agent(agent.agent_id)
    assert reloaded.attached_rag_ids == []
    assert "rag_class10_english" not in reloaded.attached_rag_ids

    # TEST 9: Re-attach the removed RAG
    updated = svc.attach_rag(agent.agent_id, "rag_b_test")
    assert updated.attached_rag_ids == ["rag_b_test"]
    reloaded = svc.get_agent(agent.agent_id)
    assert reloaded.attached_rag_ids == ["rag_b_test"]
