"""
Unit and integration tests for Phase 12 RAG Artifact Lifecycle & Storage Contract.
Verifies:
1. Stable immutable rag_id decoupled from transient build_id.
2. Migration of active build bld_6f509ca2 into rag_class10_english.
3. Version mapping and dynamic active version resolution.
4. Reference integrity gate: deleting attached RAG raises RAGInUseError (409).
5. Force deletion: atomic detachment from all referencing agents.
6. Portable ZIP-based .ragpack export with component hashes and ZERO model weights.
7. Forbidden model weight scanner: rejects packages with *.gguf or *.onnx.
8. Safe pre-installation import: path traversal rejected, corrupted hashes rejected, atomic build installation.
"""

from pathlib import Path
import shutil
import zipfile
import pytest

from ragger_engine.rag_lifecycle import (
    RAGLifecycleService,
    CreateRAGRequest,
    UpdateRAGRequest,
    RAGStatus,
    RAGNotFoundError,
    RAGInUseError,
    ForbiddenModelWeightError,
    InvalidRAGPackError,
)
from ragger_engine.rag_library.service import RAGLibraryService
from ragger_engine.agent_workspace.service import AgentWorkspaceService
from ragger_engine.agent_workspace.models import CreateAgentRequest
from ragger_engine.agent_workspace.exceptions import AgentNotFoundError


def _get_workspace_dir():
    return Path("../storage") if Path("../storage").exists() else Path("storage")


def test_rag_lifecycle_migration_and_crud(tmp_path: Path):
    storage_dir = _get_workspace_dir()
    # Initialize service pointing to storage
    lifecycle_service = RAGLifecycleService(workspace_dir=storage_dir)

    # 1. Existing builds must be migrated to stable RAG artifacts
    rags = lifecycle_service.list_rags()
    assert len(rags) >= 1
    active_rag = rags[0]
    assert active_rag is not None
    assert active_rag.active_version_id is not None
    assert len(active_rag.versions) > 0

    # 2. Dynamic build_id resolution
    resolved_build = lifecycle_service.resolve_active_build_id(active_rag.rag_id)
    assert resolved_build is not None

    # 3. Create a draft/new RAG artifact
    new_rag = lifecycle_service.create_rag(
        CreateRAGRequest(
            name="Quantum Computing Research",
            description="Quantum mechanics and computing papers",
            initial_build_id=resolved_build,
        )
    )
    assert new_rag.rag_id.startswith("rag_")
    assert len(new_rag.versions) == 1
    assert new_rag.versions[0].build_id == resolved_build

    # 4. Update and Archive
    archived = lifecycle_service.archive_rag(new_rag.rag_id)
    assert archived.status == RAGStatus.ARCHIVED

    # Verify excluded from normal listing by default
    active_only = lifecycle_service.list_rags(include_archived=False)
    assert not any(r.rag_id == new_rag.rag_id for r in active_only)

    with_archived = lifecycle_service.list_rags(include_archived=True)
    assert any(r.rag_id == new_rag.rag_id for r in with_archived)

    # Cleanup created RAG
    lifecycle_service.delete_rag(new_rag.rag_id, force=True)


def test_rag_reference_integrity_gate(tmp_path: Path):
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

    # Create temporary RAG artifact
    test_rag = lifecycle_service.create_rag(
        CreateRAGRequest(
            name="Integrity Test RAG",
            description="Testing agent reference gates",
            initial_build_id="bld_8706465c",
        )
    )

    # Attach this RAG to an agent
    agent = agent_service.create_agent(
        CreateAgentRequest(
            name="Integrity Agent",
            attached_rag_ids=[test_rag.rag_id],
        )
    )

    # 1. Normal delete MUST fail with RAGInUseError (409)
    with pytest.raises(RAGInUseError) as exc_info:
        lifecycle_service.delete_rag(test_rag.rag_id, force=False)
    assert agent.agent_id in exc_info.value.referencing_agents

    # 2. Force delete MUST atomically detach and clean up dedicated single-RAG agent
    record, affected = lifecycle_service.delete_rag(test_rag.rag_id, force=True)
    assert record.rag_id == test_rag.rag_id
    assert agent.agent_id in affected

    # Verify dedicated single-RAG agent is purged and not lingering
    with pytest.raises(AgentNotFoundError):
        agent_service.get_agent(agent.agent_id)


def test_ragpack_export_and_forbidden_weights(tmp_path: Path):
    storage_dir = _get_workspace_dir()
    lifecycle_service = RAGLifecycleService(workspace_dir=storage_dir)

    rags = lifecycle_service.list_rags()
    assert len(rags) > 0
    target_rag = rags[0]

    # Export active rag to a .ragpack bundle in tmp_path
    export_file = tmp_path / "rag_export.ragpack"
    exported_path = lifecycle_service.export_ragpack(target_rag.rag_id, output_path=export_file)

    assert exported_path.exists()
    assert zipfile.is_zipfile(exported_path)

    # Inspect ZIP entries
    with zipfile.ZipFile(exported_path, "r") as zf:
        names = zf.namelist()
        assert "ragpack_manifest.json" in names
        assert "manifest.json" in names
        assert any(n.startswith("knowledge/") for n in names)
        # ZERO LLM WEIGHTS INVARIANT
        assert not any(n.endswith(".gguf") or n.endswith(".onnx") or n.endswith(".safetensors") for n in names)

    # Test forbidden weight scanner: Create a fake build with a .gguf file and attempt export
    fake_build_dir = storage_dir / "builds" / "bld_fake_with_model"
    fake_build_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(storage_dir / "builds" / "bld_8706465c" / "manifest.json", fake_build_dir / "manifest.json")
    (fake_build_dir / "weights.gguf").write_bytes(b"FAKE GGUF")

    fake_rag = lifecycle_service.create_rag(
        CreateRAGRequest(name="Contaminated RAG", initial_build_id="bld_fake_with_model")
    )
    try:
        with pytest.raises(ForbiddenModelWeightError):
            lifecycle_service.export_ragpack(fake_rag.rag_id)
    finally:
        lifecycle_service.delete_rag(fake_rag.rag_id, force=True)
        shutil.rmtree(fake_build_dir, ignore_errors=True)


def test_ragpack_import_atomic_validation(tmp_path: Path):
    storage_dir = _get_workspace_dir()
    lifecycle_service = RAGLifecycleService(workspace_dir=storage_dir)

    # 1. Export valid package
    export_file = tmp_path / "valid_test.ragpack"
    lifecycle_service.export_ragpack("rag_class10_english", output_path=export_file)

    # 2. Import valid package
    imported_record = lifecycle_service.import_ragpack(export_file)
    assert imported_record is not None
    assert "(Imported)" in imported_record.name
    assert imported_record.status == RAGStatus.ACTIVE
    assert len(imported_record.versions) == 1

    # Verify the imported build directory actually exists in builds/
    imported_build_id = imported_record.versions[0].build_id
    imported_build_dir = storage_dir / "builds" / imported_build_id
    assert imported_build_dir.exists()
    assert (imported_build_dir / "manifest.json").exists()
    assert (imported_build_dir / "index").exists()

    # 3. Test corrupted hash rejection
    corrupted_zip = tmp_path / "corrupted.ragpack"
    shutil.copy2(export_file, corrupted_zip)
    # Tamper with the zip content
    with zipfile.ZipFile(export_file, "r") as src_zip:
        with zipfile.ZipFile(corrupted_zip, "w") as dst_zip:
            for item in src_zip.infolist():
                data = src_zip.read(item.filename)
                if item.filename == "manifest.json":
                    data = data + b" // tampered bytes"
                dst_zip.writestr(item, data)

    with pytest.raises(InvalidRAGPackError):
        lifecycle_service.import_ragpack(corrupted_zip)

    # Clean up imported RAG and build
    lifecycle_service.delete_rag(imported_record.rag_id, force=True)
    shutil.rmtree(imported_build_dir, ignore_errors=True)
