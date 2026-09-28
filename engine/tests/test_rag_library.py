import pytest
from pathlib import Path
from ragger_engine.rag_library.service import RAGLibraryService
from ragger_engine.rag_library.models import RAGArtifact, RAGArtifactDetail


def _get_workspace_dir():
    return Path("../storage") if Path("../storage").exists() else Path("storage")


def test_rag_library_discovery(tmp_path: Path):
    workspace_dir = _get_workspace_dir()
    service = RAGLibraryService(workspace_dir=workspace_dir)

    artifacts = service.list_artifacts()
    assert isinstance(artifacts, list)
    assert len(artifacts) > 0

    # Ensure build bld_8706465c is discovered
    active_arts = [a for a in artifacts if a.build_id == "bld_8706465c"]
    assert len(active_arts) == 1
    art = active_arts[0]
    assert art.chunk_count == 235
    assert art.approved_architecture == "hybrid_rag"
    assert len(art.sources) > 0

    # Ensure at least one build in artifacts reflects the active state according to active_build.json
    active_id = service._get_active_build_id()
    if active_id:
        active_marked = [a for a in artifacts if a.is_active]
        assert len(active_marked) == 1
        assert active_marked[0].build_id == active_id


def test_rag_library_detail():
    workspace_dir = _get_workspace_dir()
    service = RAGLibraryService(workspace_dir=workspace_dir)

    detail = service.get_artifact_detail("bld_8706465c")
    assert detail is not None
    assert isinstance(detail, RAGArtifactDetail)
    assert detail.build_id == "bld_8706465c"
    assert detail.chunk_count == 235
    assert len(detail.sample_chunks) > 0
    assert detail.sample_chunks[0].chunk_id.startswith("chk_")


def test_rag_library_nonexistent_build():
    workspace_dir = _get_workspace_dir()
    service = RAGLibraryService(workspace_dir=workspace_dir)

    detail = service.get_artifact_detail("bld_nonexistent_xyz")
    assert detail is None
