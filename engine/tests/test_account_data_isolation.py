"""
Tests for Account Data Isolation & Clean Initial Account State.

Invariants Verified:
1. When Account A registers / creates a RAG artifact, it is scoped to Account A.
2. When Account B registers / queries RAG artifacts, it starts completely empty (0 RAGs).
3. Account B cannot see or retrieve Account A's RAG artifacts (returns 404 / RAGNotFoundError).
4. Account B cannot delete Account A's RAG artifacts.
5. New accounts automatically receive a clean default agent with 0 attached RAGs.
6. Account A's agents are not visible to Account B.
7. Account A's RAG attachments are isolated and do not bleed into Account B's workspace.
8. Account A's data remains persistent and accessible upon re-login.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from ragger_engine.rag_lifecycle.service import RAGLifecycleService
from ragger_engine.rag_lifecycle.models import CreateRAGRequest, RAGStatus
from ragger_engine.rag_lifecycle.exceptions import RAGNotFoundError
from ragger_engine.agent_workspace.service import AgentWorkspaceService
from ragger_engine.agent_workspace.models import CreateAgentRequest, UpdateAgentRequest
from ragger_engine.agent_workspace.exceptions import AgentNotFoundError, RAGArtifactNotFoundError


@pytest.fixture
def workspace_dir(tmp_path):
    d = tmp_path / "account_isolation_workspace"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def lifecycle_service(workspace_dir):
    return RAGLifecycleService(workspace_dir=workspace_dir)


@pytest.fixture
def agent_service(workspace_dir, lifecycle_service):
    mock_lib = MagicMock()
    mock_lib.list_artifacts.return_value = []
    svc = AgentWorkspaceService(
        workspace_dir=workspace_dir,
        rag_library_service=mock_lib,
        generation_service=MagicMock(),
        rag_lifecycle_service=lifecycle_service,
    )
    lifecycle_service.agent_workspace_service = svc
    return svc


def test_clean_initial_account_state(lifecycle_service, agent_service):
    """A newly registered account (Account B) starts with 0 RAGs and a clean default agent with 0 attached RAGs."""
    account_b_id = "acc_user_b"

    # 1. RAG Library for Account B is empty
    account_b_rags = lifecycle_service.list_rags(account_id=account_b_id)
    assert len(account_b_rags) == 0

    # 2. Agent Workspace for Account B initializes an empty default agent
    agents = agent_service.list_agents(account_id=account_b_id)
    assert len(agents) == 1
    assert agents[0].account_id == account_b_id
    assert agents[0].attached_rag_ids == []


def test_rag_creation_and_listing_isolation(lifecycle_service):
    """RAGs created by Account A are strictly isolated from Account B."""
    acc_a = "acc_alpha"
    acc_b = "acc_beta"

    # Account A creates a RAG
    rag_a = lifecycle_service.create_rag(
        CreateRAGRequest(name="Alpha Secret Specs", description="Classified doc"),
        account_id=acc_a,
    )
    assert rag_a.account_id == acc_a

    # Account A can list it
    rags_for_a = lifecycle_service.list_rags(account_id=acc_a)
    assert len(rags_for_a) == 1
    assert rags_for_a[0].rag_id == rag_a.rag_id

    # Account B sees 0 RAGs
    rags_for_b = lifecycle_service.list_rags(account_id=acc_b)
    assert len(rags_for_b) == 0

    # Account B cannot fetch Account A's RAG by ID
    with pytest.raises(RAGNotFoundError):
        lifecycle_service.get_rag(rag_a.rag_id, account_id=acc_b)

    # Account A can fetch its own RAG by ID
    fetched_a = lifecycle_service.get_rag(rag_a.rag_id, account_id=acc_a)
    assert fetched_a.rag_id == rag_a.rag_id


def test_cross_account_rag_deletion_rejection(lifecycle_service):
    """Account B cannot delete Account A's RAG artifact."""
    acc_a = "acc_alpha"
    acc_b = "acc_beta"

    rag_a = lifecycle_service.create_rag(
        CreateRAGRequest(name="Alpha Financials"),
        account_id=acc_a,
    )

    # Account B attempts deletion -> must raise RAGNotFoundError (access rejected)
    with pytest.raises(RAGNotFoundError):
        lifecycle_service.delete_rag(rag_a.rag_id, force=True, account_id=acc_b)

    # Verify RAG A is still intact and owned by Account A
    assert lifecycle_service.get_rag(rag_a.rag_id, account_id=acc_a).name == "Alpha Financials"

    # Account A deletes its own RAG -> succeeds
    rec, unlinked = lifecycle_service.delete_rag(rag_a.rag_id, force=True, account_id=acc_a)
    assert rec.rag_id == rag_a.rag_id
    assert len(lifecycle_service.list_rags(account_id=acc_a)) == 0


def test_agent_workspace_account_isolation(lifecycle_service, agent_service):
    """Agents created by Account A are completely hidden and inaccessible to Account B."""
    acc_a = "acc_alpha"
    acc_b = "acc_beta"

    # Account A creates a RAG and an Agent attached to it
    rag_a = lifecycle_service.create_rag(
        CreateRAGRequest(name="Alpha Knowledge"),
        account_id=acc_a,
    )

    agent_a = agent_service.create_agent(
        CreateAgentRequest(
            name="Alpha Agent",
            description="Agent for Alpha",
            attached_rag_ids=[rag_a.rag_id],
        ),
        account_id=acc_a,
    )
    assert agent_a.account_id == acc_a
    assert agent_a.attached_rag_ids == [rag_a.rag_id]

    # Account B lists agents -> sees only its own default agent, NOT Alpha Agent
    agents_b = agent_service.list_agents(account_id=acc_b)
    assert len(agents_b) == 1
    assert agents_b[0].agent_id != agent_a.agent_id
    assert agents_b[0].account_id == acc_b

    # Account B cannot get Account A's agent
    with pytest.raises(AgentNotFoundError):
        agent_service.get_agent(agent_a.agent_id, account_id=acc_b)

    # Account B cannot attach Account A's RAG to its own agent
    default_agent_b = agents_b[0]
    with pytest.raises(RAGArtifactNotFoundError):
        agent_service.attach_rag(default_agent_b.agent_id, rag_a.rag_id, account_id=acc_b)


def test_multi_account_persistence_and_restoration(lifecycle_service, agent_service):
    """Account A logs out, Account B does work, then Account A logs back in with all data intact."""
    acc_a = "acc_user_101"
    acc_b = "acc_user_202"

    # 1. User A creates 2 RAGs
    rag_a1 = lifecycle_service.create_rag(CreateRAGRequest(name="A Docs 1"), account_id=acc_a)
    rag_a2 = lifecycle_service.create_rag(CreateRAGRequest(name="A Docs 2"), account_id=acc_a)
    assert len(lifecycle_service.list_rags(account_id=acc_a)) == 2

    # 2. User A logs out -> User B logs in (clean state)
    assert len(lifecycle_service.list_rags(account_id=acc_b)) == 0

    # User B creates 1 RAG
    rag_b1 = lifecycle_service.create_rag(CreateRAGRequest(name="B Workspace"), account_id=acc_b)
    assert len(lifecycle_service.list_rags(account_id=acc_b)) == 1

    # 3. User B logs out -> User A logs back in
    restored_a = lifecycle_service.list_rags(account_id=acc_a)
    assert len(restored_a) == 2
    restored_ids = {r.rag_id for r in restored_a}
    assert rag_a1.rag_id in restored_ids
    assert rag_a2.rag_id in restored_ids
    assert rag_b1.rag_id not in restored_ids
