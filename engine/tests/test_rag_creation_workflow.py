"""
Unit and integration tests for Phase 13 RAG Creation, Version Registration, Rollback, Comparison,
and Agent Dynamic Version Resolution.

Verifies:
1. Creating a new RAG artifact with deterministic, stable rag_id.
2. Registering a new build as a new version (e.g. v1.1.0) under an existing RAG.
3. Atomic version activation: active_version_id updates strictly inside RAG record.
4. Agents attached to rag_id dynamically resolve the new active version without reattachment.
5. Version rollback: rolling back to v1.0.0 updates active_version_id, and agent resolves v1.0.0.
6. Failed builds do NOT create or corrupt any RAG version or active pointer.
7. Objective Version Comparison: compares chunk delta, vector delta, sources delta, embedding model, and manifest hashes.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import pytest

from ragger_engine.rag_lifecycle import (
    RAGLifecycleService,
    CreateRAGRequest,
    RegisterVersionRequest,
    RAGStatus,
    RAGNotFoundError,
    RAGVersionNotFoundError,
)
from ragger_engine.rag_library.service import RAGLibraryService
from ragger_engine.agent_workspace.service import AgentWorkspaceService
from ragger_engine.agent_workspace.models import CreateAgentRequest


def _get_workspace_dir():
    return Path("../storage") if Path("../storage").exists() else Path("storage")


def test_rag_creation_and_version_registration_flow(tmp_path: Path):
    storage_dir = _get_workspace_dir()
    rag_lib = RAGLibraryService(workspace_dir=storage_dir)
    agent_service = AgentWorkspaceService(
        workspace_dir=storage_dir,
        rag_library_service=rag_lib,
        generation_service=None,
    )
    lifecycle_service = RAGLifecycleService(
        workspace_dir=storage_dir,
        agent_workspace_service=agent_service,
    )
    agent_service.rag_lifecycle_service = lifecycle_service

    # 1. Create a brand new RAG Knowledge Artifact
    rag_name = f"Test Studio RAG {tmp_path.name}"
    new_rag = lifecycle_service.create_rag(
        CreateRAGRequest(
            name=rag_name,
            description="Created via Phase 13 Studio integration test",
            initial_build_id="bld_8706465c",
        )
    )
    assert new_rag.rag_id.startswith("rag_")
    assert len(new_rag.versions) == 1
    v1 = new_rag.versions[0]
    assert v1.build_id == "bld_8706465c"
    assert new_rag.active_version_id == v1.version_id

    # 2. Attach an agent to this stable rag_id
    agent = agent_service.create_agent(
        CreateAgentRequest(
            name="Workflow Test Agent",
            description="Agent testing dynamic version resolution",
            attached_rag_ids=[new_rag.rag_id],
        )
    )
    assert new_rag.rag_id in agent.attached_rag_ids

    # Verify agent resolves to initial build bld_8706465c
    resolved_build_v1 = lifecycle_service.resolve_active_build_id(new_rag.rag_id)
    assert resolved_build_v1 == "bld_8706465c"

    # 3. Register a second version (v1.1.0) using a simulated second build
    # Create simulated build directory bld_sim_test
    sim_build_id = f"bld_sim_{tmp_path.name[:8]}"
    sim_build_dir = storage_dir / "builds" / sim_build_id
    sim_build_dir.mkdir(parents=True, exist_ok=True)

    # Copy manifest and modify metrics
    src_manifest = storage_dir / "builds" / "bld_8706465c" / "manifest.json"
    with open(src_manifest, "r", encoding="utf-8") as f:
        m_data = json.load(f)
    m_data["build_id"] = sim_build_id
    m_data["chunk_count"] = 312
    m_data["vector_count"] = 312
    m_data["manifest_hash"] = "simulated_hash_v1_1_0"
    m_data["source_ids"].append("src_supplementary_test")
    with open(sim_build_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(m_data, f, indent=2)

    try:
        # Register v1.1.0 as active version
        v2 = lifecycle_service.register_version(
            new_rag.rag_id,
            RegisterVersionRequest(
                build_id=sim_build_id,
                version_tag="v1.1.0",
                set_active=True,
            ),
        )
        assert v2.version_tag == "v1.1.0"
        assert v2.build_id == sim_build_id
        assert v2.chunk_count == 312

        # Verify active version in RAG artifact updated
        updated_rag = lifecycle_service.get_rag(new_rag.rag_id)
        assert updated_rag.active_version_id == v2.version_id
        assert len(updated_rag.versions) == 2

        # 4. Agent dynamic resolution: Agent still points to new_rag.rag_id,
        # but now automatically resolves to sim_build_id WITHOUT ANY AGENT PROFILE CHANGE
        agent_after = agent_service.get_agent(agent.agent_id)
        assert agent_after.attached_rag_ids == [new_rag.rag_id]  # Unchanged!
        resolved_build_v2 = lifecycle_service.resolve_active_build_id(new_rag.rag_id)
        assert resolved_build_v2 == sim_build_id

        # 5. Objective Version Comparison: Compare v1.0.0 and v1.1.0
        comparison = lifecycle_service.compare_versions(
            rag_id=new_rag.rag_id,
            base_version_id=v1.version_id,
            target_version_id=v2.version_id,
        )
        assert comparison.rag_id == new_rag.rag_id
        assert comparison.base_version_tag == "v1.0.0"
        assert comparison.target_version_tag == "v1.1.0"
        assert comparison.chunk_count_delta == 312 - 235
        assert comparison.vector_count_delta == 312 - 235
        assert comparison.manifest_hash_changed is True
        assert "src_supplementary_test" in comparison.sources_added

        # 6. Version Rollback: Roll back to v1.0.0
        rolled_back_rag = lifecycle_service.rollback_version(new_rag.rag_id, v1.version_id)
        assert rolled_back_rag.active_version_id == v1.version_id

        # Agent now dynamically resolves back to bld_8706465c
        resolved_after_rollback = lifecycle_service.resolve_active_build_id(new_rag.rag_id)
        assert resolved_after_rollback == "bld_8706465c"

    finally:
        # Cleanup test entities
        if sim_build_dir.exists():
            shutil.rmtree(sim_build_dir, ignore_errors=True)
        agent_service.delete_agent(agent.agent_id)
        lifecycle_service.delete_rag(new_rag.rag_id, force=True)


def test_build_failure_creates_no_version(tmp_path: Path):
    """
    Guarantees that a failed or aborted build creates zero versions,
    preserving the current active version completely intact.
    """
    storage_dir = _get_workspace_dir()
    lifecycle_service = RAGLifecycleService(workspace_dir=storage_dir)

    rags = lifecycle_service.list_rags()
    assert len(rags) > 0
    target_rag_id = rags[0].rag_id

    rag_before = lifecycle_service.get_rag(target_rag_id)
    initial_version_count = len(rag_before.versions)
    initial_active_id = rag_before.active_version_id

    # Attempt to register a non-existent build (simulating a failed build that never produced manifest)
    with pytest.raises(Exception):
        lifecycle_service.register_version(
            target_rag_id,
            RegisterVersionRequest(
                build_id="bld_non_existent_failed_build",
                version_tag="v9.9.9",
                set_active=True,
            ),
        )

    # Confirm zero corruption: version count and active pointer are strictly preserved
    rag_after = lifecycle_service.get_rag(target_rag_id)
    assert len(rag_after.versions) == initial_version_count
    assert rag_after.active_version_id == initial_active_id
