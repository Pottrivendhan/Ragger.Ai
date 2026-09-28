"""
Active Build Snapshot and Integrity Verification for Phase 8 Quality Evaluation.
Enforces that evaluation is strictly coupled to an immutable build snapshot and detects
any build pointer changes occurring during evaluation runs (raising HTTP 409).
"""

import json
from pathlib import Path
from typing import Optional

from ragger_engine.builder.models import BuildManifest
from .exceptions import (
    ArchitectureNotEvaluableError,
    EvaluationBuildChangedError,
    EvaluationError,
    NoActiveBuildError,
)
from .models import BuildSnapshot


def capture_build_snapshot(workspace_dir: Path, workspace_id: str) -> BuildSnapshot:
    """
    Captures an immutable snapshot of the active build at evaluation preflight.
    Verifies manifest hash and rejects deferred architectures (e.g. Graph RAG).
    """
    active_pointer_file = workspace_dir / "active_build.json"
    if not active_pointer_file.exists():
        raise NoActiveBuildError(workspace_id)

    try:
        with open(active_pointer_file, "r", encoding="utf-8") as f:
            pointer = json.load(f)
    except Exception as e:
        raise NoActiveBuildError(workspace_id) from e

    build_id = pointer.get("active_build_id")
    expected_hash = pointer.get("manifest_hash")
    if not build_id or not expected_hash:
        raise NoActiveBuildError(workspace_id)

    return capture_build_snapshot_for_build(workspace_dir, build_id)


def capture_build_snapshot_for_build(
    workspace_dir: Path,
    build_id: str,
    rag_id: Optional[str] = None,
    version_id: Optional[str] = None,
    version_tag: Optional[str] = None,
) -> BuildSnapshot:
    """
    Captures an immutable snapshot directly for a specified build_id.
    Used for version-scoped evaluation where build_id is resolved from RAGLifecycleService.
    Verifies manifest hash and rejects deferred architectures (e.g. Graph RAG).
    """
    manifest_file = workspace_dir / "builds" / build_id / "manifest.json"
    if not manifest_file.exists():
        raise EvaluationError(f"Build manifest missing for build '{build_id}'")

    try:
        with open(manifest_file, "r", encoding="utf-8") as f:
            raw_manifest = json.load(f)
        manifest = BuildManifest.model_validate(raw_manifest)
    except Exception as e:
        raise EvaluationError(f"Failed to parse build manifest for '{build_id}': {str(e)}") from e

    if manifest.status != "completed":
        raise EvaluationError(f"Build '{build_id}' is not in completed state (status: '{manifest.status}')")

    # Architecture gate: Graph RAG is not evaluable
    if manifest.approved_architecture == "graph_rag":
        raise ArchitectureNotEvaluableError(manifest.approved_architecture)

    # Cryptographic integrity check
    recomputed_hash = BuildManifest.compute_manifest_hash(manifest.model_dump())
    if recomputed_hash != manifest.manifest_hash:
        raise EvaluationError(f"Build manifest hash corrupted for build '{build_id}'")

    return BuildSnapshot(
        build_id=manifest.build_id,
        manifest_id=manifest.manifest_id,
        manifest_hash=manifest.manifest_hash,
        approved_architecture=manifest.approved_architecture,
        source_ids=list(manifest.source_ids),
        source_sha256=dict(manifest.source_hashes),
        chunk_count=manifest.chunk_count,
        vector_count=manifest.vector_count,
        rag_id=rag_id,
        version_id=version_id,
        version_tag=version_tag,
    )


def verify_build_integrity(workspace_dir: Path, snapshot: BuildSnapshot) -> None:
    """
    Re-verifies build integrity against preflight snapshot before persisting report.
    - If version-scoped (snapshot.rag_id and snapshot.version_id present), verifies that
      the evaluated build directory and its manifest hash on disk remain intact (active version
      mutations elsewhere in the workspace do not fail the evaluation).
    - If legacy mode (no rag_id/version_id), re-verifies active_build.json pointer against snapshot.
    """
    if snapshot.rag_id is not None and snapshot.version_id is not None:
        manifest_file = workspace_dir / "builds" / snapshot.build_id / "manifest.json"
        if not manifest_file.exists():
            raise EvaluationBuildChangedError(snapshot.build_id, "MISSING_ON_DISK")

        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                raw_manifest = json.load(f)
            manifest = BuildManifest.model_validate(raw_manifest)
        except Exception:
            raise EvaluationBuildChangedError(snapshot.build_id, "CORRUPTED_ON_DISK")

        recomputed_hash = BuildManifest.compute_manifest_hash(manifest.model_dump())
        if recomputed_hash != snapshot.manifest_hash:
            raise EvaluationBuildChangedError(snapshot.build_id, "HASH_MISMATCH")
        return

    # Legacy mode: verify active_build.json pointer
    active_pointer_file = workspace_dir / "active_build.json"
    if not active_pointer_file.exists():
        raise EvaluationBuildChangedError(snapshot.build_id, "NONE")

    try:
        with open(active_pointer_file, "r", encoding="utf-8") as f:
            pointer = json.load(f)
    except Exception:
        raise EvaluationBuildChangedError(snapshot.build_id, "CORRUPTED")

    current_build_id = pointer.get("active_build_id")
    current_hash = pointer.get("manifest_hash")

    if current_build_id != snapshot.build_id or current_hash != snapshot.manifest_hash:
        raise EvaluationBuildChangedError(snapshot.build_id, current_build_id or "UNKNOWN")
