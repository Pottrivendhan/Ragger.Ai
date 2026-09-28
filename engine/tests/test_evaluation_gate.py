"""
Unit tests for Phase 8 evaluation gates and security boundaries.
Verifies Ollama zero-pull enforcement, test judge environment gating,
Graph RAG rejection, and active build preflight requirements.
"""

import json
import os
from pathlib import Path
import pytest

from ragger_engine.evaluation.exceptions import (
    ArchitectureNotEvaluableError,
    EvaluationError,
    ModelNotAvailableError,
    NoActiveBuildError,
)
from ragger_engine.evaluation.models import EvaluationConfig
from ragger_engine.evaluation.providers.factory import get_eval_judge
from ragger_engine.evaluation.providers.ollama import OllamaEvalJudge
from ragger_engine.evaluation.providers.test_judge import TestDeterministicEvalJudge
from ragger_engine.evaluation.snapshot import capture_build_snapshot


def test_test_judge_environment_gate(monkeypatch):
    monkeypatch.delenv("RAGGER_ALLOW_TEST_EVAL", raising=False)
    with pytest.raises(EvaluationError) as exc_info:
        TestDeterministicEvalJudge()
    assert exc_info.value.code == "TEST_EVAL_FORBIDDEN"

    # Now enable gate
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EVAL", "1")
    judge = TestDeterministicEvalJudge()
    judge.validate_availability()


def test_ollama_judge_unavailable_without_pull():
    """Verify OllamaEvalJudge checks local tags and raises ModelNotAvailableError when unreachable."""
    judge = OllamaEvalJudge(host="127.0.0.1", port=65530, model_name="nonexistent:model")
    with pytest.raises(ModelNotAvailableError) as exc_info:
        judge.validate_availability()
    assert exc_info.value.code == "MODEL_NOT_AVAILABLE"


def test_graph_rag_architecture_rejection(tmp_path):
    workspace_dir = tmp_path / "ws"
    workspace_dir.mkdir()

    build_id = "bld_graph_01"
    build_dir = workspace_dir / "builds" / build_id
    build_dir.mkdir(parents=True)

    # Manifest specifying graph_rag
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    manifest_data = {
        "manifest_id": "mnf_graph",
        "workspace_id": "ws",
        "build_id": build_id,
        "config_id": "cfg_01",
        "config_version": 1,
        "config_hash": "cfg_hash",
        "source_ids": ["src_01"],
        "source_hashes": {"src_01": "h1"},
        "approved_architecture": "graph_rag",
        "chunking_config": {"strategy": "semantic", "chunk_size": 256, "chunk_overlap": 32},
        "embedding_config": {"model_name": "all-minilm-l6-v2", "dimension": 384, "batch_size": 16, "device": "cpu"},
        "vector_db_config": {"provider": "chroma", "collection_name": "rag", "metric": "cosine"},
        "retrieval_config": {"top_k": 5, "enable_reranking": False},
        "chunk_count": 5,
        "vector_count": 5,
        "embedding_dimension": 384,
        "embedding_model": "all-minilm-l6-v2",
        "vector_store": "chroma",
        "started_at": now,
        "completed_at": now,
        "build_duration_ms": 100.0,
        "status": "completed",
    }
    from ragger_engine.builder.models import BuildManifest
    manifest_hash = BuildManifest.compute_manifest_hash(manifest_data)
    manifest_data["manifest_hash"] = manifest_hash

    with open(build_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest_data, f)

    # Active build pointer
    with open(workspace_dir / "active_build.json", "w", encoding="utf-8") as f:
        json.dump({"active_build_id": build_id, "manifest_hash": manifest_hash}, f)

    with pytest.raises(ArchitectureNotEvaluableError) as exc_info:
        capture_build_snapshot(workspace_dir, "ws")
    assert exc_info.value.code == "ARCHITECTURE_NOT_EVALUATABLE"


def test_no_active_build_rejection(tmp_path):
    empty_dir = tmp_path / "empty_ws"
    empty_dir.mkdir()
    with pytest.raises(NoActiveBuildError) as exc_info:
        capture_build_snapshot(empty_dir, "empty_ws")
    assert exc_info.value.code == "NO_ACTIVE_BUILD"
