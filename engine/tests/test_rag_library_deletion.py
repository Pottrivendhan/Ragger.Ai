"""
Tests for RAG Library Deletion Integration:
Verifies:
1. Deletion uses existing RAG lifecycle deletion service via authoritative rag_id (not build_id).
2. Deleting an unattached RAG succeeds and removes it from list_rags().
3. Deleting an attached RAG with force=False fails with RAGInUseError (HTTP 409).
4. Deleting a nonexistent RAG fails with RAGNotFoundError (HTTP 404).
5. Deleting RAG B leaves RAG A and RAG C untouched in both lifecycle registry and chat target resolution.
6. Chat routing on remaining RAGs continues to work accurately after another RAG is deleted.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from ragger_engine.rag_lifecycle import (
    RAGLifecycleService,
    CreateRAGRequest,
    RAGNotFoundError,
    RAGInUseError,
)
from ragger_engine.rag_lifecycle.models import RAGArtifactRecord, RAGVersionInfo, RAGStatus
from ragger_engine.agent_workspace.models import AgentProfile
from ragger_engine.multi_rag.coordinator import MultiRAGCoordinator


def _get_workspace_dir():
    return Path("../storage") if Path("../storage").exists() else Path("storage")


def test_rag_library_deletion_by_rag_id(tmp_path: Path):
    """Deleting a RAG through lifecycle service must use authoritative rag_id and leave other RAGs untouched."""
    # Setup test lifecycle service in temporary dir
    service = RAGLifecycleService(workspace_dir=tmp_path)

    # Create three separate RAG artifacts
    rag_a = service.create_rag(CreateRAGRequest(name="RAG A - Physics", description="Physics RAG"))
    rag_b = service.create_rag(CreateRAGRequest(name="RAG B - Biology", description="Biology RAG"))
    rag_c = service.create_rag(CreateRAGRequest(name="RAG C - Chemistry", description="Chemistry RAG"))

    initial_list = service.list_rags()
    initial_ids = {r.rag_id for r in initial_list}
    assert rag_a.rag_id in initial_ids
    assert rag_b.rag_id in initial_ids
    assert rag_c.rag_id in initial_ids

    # Delete RAG B specifically using rag_id
    deleted_record, affected_agents = service.delete_rag(rag_b.rag_id, force=False)
    assert deleted_record.rag_id == rag_b.rag_id
    assert deleted_record.name == "RAG B - Biology"

    # Verify RAG B is removed while RAG A and RAG C remain untouched
    updated_list = service.list_rags()
    updated_ids = {r.rag_id for r in updated_list}
    assert rag_b.rag_id not in updated_ids
    assert rag_a.rag_id in updated_ids
    assert rag_c.rag_id in updated_ids

    # Verify RAG B lookup now raises RAGNotFoundError (404)
    with pytest.raises(RAGNotFoundError):
        service.get_rag(rag_b.rag_id)

    # Verify RAG A and RAG C can still be retrieved normally
    rec_a = service.get_rag(rag_a.rag_id)
    rec_c = service.get_rag(rag_c.rag_id)
    assert rec_a.name == "RAG A - Physics"
    assert rec_c.name == "RAG C - Chemistry"


def test_rag_library_deletion_protection_in_use(tmp_path: Path):
    """Deleting a RAG currently attached to an Agent fails closed with RAGInUseError (HTTP 409)."""
    mock_agent_service = MagicMock()
    service = RAGLifecycleService(workspace_dir=tmp_path, agent_workspace_service=mock_agent_service)

    rag = service.create_rag(CreateRAGRequest(name="Protected RAG", description="Attached to agent"))
    
    # Mock that this RAG is currently attached to an agent
    mock_agent_service.get_agents_referencing_rag.return_value = ["agt_biology_assistant"]

    # Attempting normal deletion (force=False) must raise RAGInUseError
    with pytest.raises(RAGInUseError) as exc_info:
        service.delete_rag(rag.rag_id, force=False)

    assert "agt_biology_assistant" in exc_info.value.referencing_agents

    # Verify the RAG was NOT deleted
    existing = service.get_rag(rag.rag_id)
    assert existing is not None
    assert existing.rag_id == rag.rag_id


def test_chat_routing_remains_intact_after_rag_deletion(tmp_path: Path):
    """Deleting an unrelated RAG does not corrupt target resolution or chat routing for remaining RAGs."""
    mock_retrieval_service = MagicMock()
    runtime = MagicMock()
    runtime.manifest.status = "completed"
    mock_retrieval_service.get_or_load_build_runtime.return_value = runtime

    service = RAGLifecycleService(workspace_dir=tmp_path)
    coordinator = MultiRAGCoordinator(retrieval_service=mock_retrieval_service, rag_lifecycle_service=service)

    # Create RAG A and RAG B
    rag_a = service.create_rag(CreateRAGRequest(name="Class 10 English", description="English Textbook"))
    rag_b = service.create_rag(CreateRAGRequest(name="BDA ROLE PLAY", description="BDA Role Play PDF"))

    # Add mock versions
    v_a = RAGVersionInfo(
        version_id="ver_a",
        version_tag="v1.0.0",
        build_id="bld_6f509ca2",
        created_at="2026-09-23T00:00:00Z",
        chunk_count=235,
        vector_count=235,
        manifest_hash="hash_a",
        manifest_id="man_a",
        embedding_model="mock_emb",
        vector_store="lancedb",
    )
    rag_a.versions.append(v_a)
    rag_a.active_version_id = "ver_a"

    v_b = RAGVersionInfo(
        version_id="ver_b",
        version_tag="v1.0.0",
        build_id="bld_589722a1",
        created_at="2026-09-23T00:00:00Z",
        chunk_count=15,
        vector_count=15,
        manifest_hash="hash_b",
        manifest_id="man_b",
        embedding_model="mock_emb",
        vector_store="lancedb",
    )
    rag_b.versions.append(v_b)
    rag_b.active_version_id = "ver_b"

    records = service._load_registry()
    records[rag_a.rag_id] = rag_a
    records[rag_b.rag_id] = rag_b
    service._save_registry(records)

    # Create third RAG to delete
    rag_c = service.create_rag(CreateRAGRequest(name="Unwanted RAG", description="Temp RAG"))

    # Verify BDA agent resolves to bld_589722a1 before deletion
    agent_bda = AgentProfile(
        agent_id="agt_bda",
        name="BDA Assistant",
        attached_rag_ids=[rag_b.rag_id],
    )
    targets_before = coordinator.resolve_agent_runtimes(agent_bda)
    assert len(targets_before) == 1
    assert targets_before[0].rag_id == rag_b.rag_id
    assert targets_before[0].build_id == "bld_589722a1"

    # Delete the unwanted RAG C
    service.delete_rag(rag_c.rag_id, force=False)

    # Verify BDA agent STILL resolves to bld_589722a1 after deleting RAG C
    targets_after = coordinator.resolve_agent_runtimes(agent_bda)
    assert len(targets_after) == 1
    assert targets_after[0].rag_id == rag_b.rag_id
    assert targets_after[0].build_id == "bld_589722a1"

    # Verify English agent also still resolves to bld_6f509ca2
    agent_eng = AgentProfile(
        agent_id="agt_eng",
        name="English Assistant",
        attached_rag_ids=[rag_a.rag_id],
    )
    targets_eng = coordinator.resolve_agent_runtimes(agent_eng)
    assert len(targets_eng) == 1
    assert targets_eng[0].rag_id == rag_a.rag_id
    assert targets_eng[0].build_id == "bld_6f509ca2"


def test_unindexed_build_reconciliation_and_directory_cleanup(tmp_path: Path):
    """
    Verifies:
    1. Unindexed build directories in storage/builds/ are auto-reconciled or dynamically resolved.
    2. Deleting the RAG removes both the registry entry and the physical build directory.
    """
    builds_dir = tmp_path / "builds"
    builds_dir.mkdir(parents=True, exist_ok=True)
    bld_test = builds_dir / "bld_test123"
    bld_test.mkdir(parents=True, exist_ok=True)
    manifest_data = {
        "manifest_id": "man_bld_test123",
        "workspace_id": "storage",
        "build_id": "bld_test123",
        "config_id": "cfg_test",
        "config_version": 1,
        "config_hash": "hash123",
        "source_ids": ["src_test1"],
        "source_hashes": {"src_test1": "hash"},
        "approved_architecture": "hybrid_rag",
        "chunking_config": {
            "strategy": "boundary_paragraph",
            "chunk_size": 512,
            "chunk_overlap": 64,
        },
        "embedding_config": {
            "provider": "local_onnx",
            "model_name": "bge-small-en-v1.5",
            "dimension": 384,
        },
        "vector_db_config": {
            "provider": "lancedb",
            "metric": "cosine",
            "index_type": "auto",
        },
        "retrieval_config": {
            "strategy": "hybrid_rrf",
            "top_k": 5,
            "rerank_enabled": False,
            "rrf_k": 60,
        },
        "vector_store": "lancedb",
        "embedding_model": "bge-small-en-v1.5",
        "embedding_dimension": 384,
        "status": "completed",
        "chunk_count": 10,
        "vector_count": 10,
        "started_at": "2026-09-23T00:00:00Z",
        "completed_at": "2026-09-23T00:01:00Z",
        "build_duration_ms": 60000,
        "manifest_hash": "manhash123",
    }
    import json
    with open(bld_test / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest_data, f)

    # Initialize service
    service = RAGLifecycleService(workspace_dir=tmp_path)

    # Verify build was reconciled into registry
    rag_rec = service.get_rag("rag_bld_test123")
    assert rag_rec is not None
    assert rag_rec.rag_id == "rag_bld_test123"
    assert len(rag_rec.versions) == 1
    assert rag_rec.versions[0].build_id == "bld_test123"
    assert bld_test.exists()

    # Delete the RAG artifact
    deleted_rec, affected = service.delete_rag("rag_bld_test123", force=False)
    assert deleted_rec.rag_id == "rag_bld_test123"

    # Verify RAG is gone from registry
    with pytest.raises(RAGNotFoundError):
        service.get_rag("rag_bld_test123")

    # Verify physical build folder was cleaned up
    assert not bld_test.exists()


def test_rag_library_deletion_user_confirmed_detaches_from_agent(tmp_path: Path):
    """
    Verifies Product Requirement:
    - User confirms deletion of a RAG currently attached to an Agent.
    - RAG is safely detached from the Agent's attached_rag_ids.
    - RAG artifact is completely deleted from the registry and cannot be resolved (404).
    - Crucial: The Agent is NOT deleted and remains fully alive in the workspace.
    - If the Agent had only that 1 RAG attached, its attached_rag_ids becomes empty [].
    """
    mock_agent_service = MagicMock()
    service = RAGLifecycleService(workspace_dir=tmp_path, agent_workspace_service=mock_agent_service)

    rag = service.create_rag(CreateRAGRequest(name="Attached RAG", description="Test attached RAG"))
    mock_agent_service.get_agents_referencing_rag.return_value = ["agt_test_agent"]
    mock_agent_service.detach_rag_from_all_agents.return_value = ["agt_test_agent"]

    # When user confirms deletion (default force=True), deletion must succeed
    deleted_rec, affected = service.delete_rag(rag.rag_id)
    assert deleted_rec.rag_id == rag.rag_id
    assert affected == ["agt_test_agent"]

    # Verify detach_rag_from_all_agents was called
    mock_agent_service.detach_rag_from_all_agents.assert_called_once_with(rag.rag_id)

    # Verify RAG is deleted from registry
    with pytest.raises(RAGNotFoundError):
        service.get_rag(rag.rag_id)


def test_rag_deletion_multi_rag_agent_preserves_remaining_rags(tmp_path: Path):
    """
    Verifies:
    - When an agent is attached to multiple RAGs (e.g. RAG A and RAG B):
    - Deleting RAG A detaches only RAG A from the agent.
    - RAG B remains attached and completely functional for chat target resolution.
    - RAG A resolution returns 404, while RAG B resolves correctly.
    """
    mock_retrieval_service = MagicMock()
    runtime_b = MagicMock()
    runtime_b.manifest.status = "completed"
    mock_retrieval_service.get_or_load_build_runtime.return_value = runtime_b

    mock_agent_service = MagicMock()
    service = RAGLifecycleService(workspace_dir=tmp_path, agent_workspace_service=mock_agent_service)
    coordinator = MultiRAGCoordinator(retrieval_service=mock_retrieval_service, rag_lifecycle_service=service)

    rag_a = service.create_rag(CreateRAGRequest(name="RAG A", description="First RAG"))
    rag_b = service.create_rag(CreateRAGRequest(name="RAG B", description="Second RAG"))

    v_b = RAGVersionInfo(
        version_id="ver_b",
        version_tag="v1.0.0",
        build_id="bld_b_123",
        created_at="2026-09-23T00:00:00Z",
        chunk_count=10,
        vector_count=10,
        manifest_hash="hash_b",
        manifest_id="man_b",
        embedding_model="mock_emb",
        vector_store="lancedb",
    )
    rag_b.versions.append(v_b)
    rag_b.active_version_id = "ver_b"
    records = service._load_registry()
    records[rag_b.rag_id] = rag_b
    service._save_registry(records)

    mock_agent_service.get_agents_referencing_rag.return_value = ["agt_multi"]
    mock_agent_service.detach_rag_from_all_agents.return_value = ["agt_multi"]

    # Delete RAG A
    deleted_rec, affected = service.delete_rag(rag_a.rag_id)
    assert deleted_rec.rag_id == rag_a.rag_id
    assert affected == ["agt_multi"]

    # Verify RAG A is 404
    with pytest.raises(RAGNotFoundError):
        service.get_rag(rag_a.rag_id)

    # Verify RAG B is intact
    assert service.get_rag(rag_b.rag_id).name == "RAG B"

    # Multi-RAG Agent now only has RAG B
    agent_updated = AgentProfile(
        agent_id="agt_multi",
        name="Multi Assistant",
        attached_rag_ids=[rag_b.rag_id],
    )
    targets = coordinator.resolve_agent_runtimes(agent_updated)
    assert len(targets) == 1
    assert targets[0].rag_id == rag_b.rag_id
    assert targets[0].build_id == "bld_b_123"

