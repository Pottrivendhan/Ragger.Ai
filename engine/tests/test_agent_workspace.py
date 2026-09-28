import pytest
from pathlib import Path
from ragger_engine.agent_workspace.service import AgentWorkspaceService
from ragger_engine.agent_workspace.models import CreateAgentRequest, UpdateAgentRequest
from ragger_engine.agent_workspace.exceptions import AgentNotFoundError, RAGArtifactNotFoundError, NoAttachedRAGError
from ragger_engine.rag_library.service import RAGLibraryService


def test_agent_workspace_crud():
    # Workspace root is parent of engine directory when running in engine/
    workspace_dir = Path("../storage") if Path("../storage").exists() else Path("storage")
    rag_service = RAGLibraryService(workspace_dir=workspace_dir)
    # Instantiate with dummy generation service for unit tests of agent management
    agent_service = AgentWorkspaceService(
        workspace_dir=workspace_dir,
        rag_library_service=rag_service,
        generation_service=None,  # Not invoked in pure CRUD tests
    )

    # 1. List agents (should have at least default agent)
    agents = agent_service.list_agents()
    assert len(agents) >= 1
    assert any(a.agent_id == "agt_default" for a in agents)

    active_artifacts = rag_service.list_artifacts()
    assert len(active_artifacts) > 0
    valid_rag_id = active_artifacts[0].rag_id

    # 2. Create new agent with valid RAG
    new_agent = agent_service.create_agent(
        CreateAgentRequest(
            name="Test Physics Tutor",
            description="Physics tutor agent",
            attached_rag_ids=[valid_rag_id],
            runtime_ref="local_gguf",
        )
    )
    assert new_agent.agent_id.startswith("agt_")
    assert new_agent.name == "Test Physics Tutor"
    assert valid_rag_id in new_agent.attached_rag_ids

    # 3. Create agent with invalid RAG fails
    with pytest.raises(RAGArtifactNotFoundError):
        agent_service.create_agent(
            CreateAgentRequest(
                name="Invalid Agent",
                attached_rag_ids=["rag_bld_nonexistent_9999"],
            )
        )

    # 4. Update agent
    updated = agent_service.update_agent(
        new_agent.agent_id,
        UpdateAgentRequest(description="Updated description"),
    )
    assert updated.description == "Updated description"

    # 5. Attach & detach RAG
    detached = agent_service.detach_rag(new_agent.agent_id, valid_rag_id)
    assert len(detached.attached_rag_ids) == 0

    reattached = agent_service.attach_rag(new_agent.agent_id, valid_rag_id)
    assert valid_rag_id in reattached.attached_rag_ids

    # 6. Delete agent
    agent_service.delete_agent(new_agent.agent_id)
    with pytest.raises(AgentNotFoundError):
        agent_service.get_agent(new_agent.agent_id)
