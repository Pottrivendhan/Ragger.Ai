"""
Tests for Phase 5 Build Gate and Invariants.
Verifies rejection of missing/unfrozen configs, tampered hashes, source drift,
disk content mutation, Graph RAG non-buildable status (Option B), missing model weights (no fake fallback),
and concurrent build collisions.
"""

import json
from pathlib import Path
import pytest
import shutil

from ragger_engine.builder.embeddings.testing import TestDeterministicEmbeddingProvider
from ragger_engine.builder.exceptions import (
    ArchitectureNotBuildableError,
    BuildAlreadyRunningError,
    BuildGateError,
    ModelNotAvailableError,
    SourceDriftError,
)
from ragger_engine.builder.service import BuilderService
from ragger_engine.ingestion.detector import FileDetector
from ragger_engine.ingestion.registry import SourceRegistry
from ragger_engine.ingestion.service import IngestionService
from ragger_engine.recommendation.models import (
    ApprovedBuildConfig,
    ChunkingConfig,
    ChunkingStrategyType,
    EmbeddingConfig,
    RagArchitectureId,
    RetrievalConfig,
    RetrievalStrategy,
    VectorDbConfig,
)
from ragger_engine.recommendation.service import RecommendationService
from ragger_engine.recommendation.validation import compute_canonical_config_hash


@pytest.fixture
def temp_workspace(tmp_path: Path):
    ws_dir = tmp_path / "test_workspace"
    ws_dir.mkdir(parents=True)
    sources_dir = ws_dir / "sources"
    sources_dir.mkdir(parents=True)

    # Create dummy source file
    doc_path = sources_dir / "policy.txt"
    doc_path.write_text("Company standard operating procedure for travel expenses.", encoding="utf-8")

    registry = SourceRegistry(storage_dir=ws_dir)
    ingestion = IngestionService(registry=registry)

    # Ingest document
    result = ingestion.ingest(str(doc_path))
    record = result.source

    rec_service = RecommendationService(storage_dir=ws_dir)

    yield {
        "ws_dir": ws_dir,
        "doc_path": doc_path,
        "source_id": record.source_id,
        "ingestion": ingestion,
        "rec_service": rec_service,
    }


def create_approved_config(
    ws_dir: Path,
    source_ids: list[str],
    arch_id: RagArchitectureId = RagArchitectureId.DOCUMENT_RAG,
    chunk_strategy: ChunkingStrategyType = ChunkingStrategyType.BOUNDARY_PARAGRAPH,
    is_frozen: bool = True,
    tamper_hash: bool = False,
    embedding_provider: str = "local_onnx",
    model_name: str = "bge-small-en-v1.5",
) -> ApprovedBuildConfig:
    chunking = ChunkingConfig(strategy=chunk_strategy, chunk_size=256, chunk_overlap=32)
    embedding = EmbeddingConfig(provider=embedding_provider, model_name=model_name, dimension=384)
    vector_db = VectorDbConfig(provider="local_flat_index", metric="cosine")
    retrieval = RetrievalConfig(strategy=RetrievalStrategy.DENSE_VECTOR_TOP_K, top_k=5)

    canonical_hash = compute_canonical_config_hash(
        architecture_id=arch_id,
        chunking_config=chunking,
        embedding_config=embedding,
        vector_db_config=vector_db,
        retrieval_config=retrieval,
        source_ids=source_ids,
    )
    stored_hash = "tampered_hash_value" if tamper_hash else canonical_hash

    config = ApprovedBuildConfig(
        config_id="cfg_test_123",
        config_version=1,
        config_hash=stored_hash,
        workspace_id=ws_dir.name,
        recommended_architecture=arch_id,
        approved_architecture=arch_id,
        user_customized=False,
        source_ids=source_ids,
        chunking_config=chunking,
        embedding_config=embedding,
        vector_db_config=vector_db,
        retrieval_config=retrieval,
        is_frozen=is_frozen,
    )
    with open(ws_dir / "approved_build_config.json", "w", encoding="utf-8") as f:
        f.write(config.model_dump_json(indent=2))
    return config


def test_gate_rejects_missing_config(temp_workspace):
    builder = BuilderService(
        workspace_dir=temp_workspace["ws_dir"],
        ingestion_service=temp_workspace["ingestion"],
        recommendation_service=temp_workspace["rec_service"],
    )
    with pytest.raises(BuildGateError) as exc:
        builder.validate_preflight()
    assert "No approved_build_config.json" in str(exc.value)


def test_gate_rejects_unfrozen_config(temp_workspace):
    create_approved_config(
        ws_dir=temp_workspace["ws_dir"],
        source_ids=[temp_workspace["source_id"]],
        is_frozen=False,
    )
    builder = BuilderService(
        workspace_dir=temp_workspace["ws_dir"],
        ingestion_service=temp_workspace["ingestion"],
        recommendation_service=temp_workspace["rec_service"],
    )
    with pytest.raises(BuildGateError) as exc:
        builder.validate_preflight()
    assert "not marked as frozen" in str(exc.value)


def test_gate_rejects_tampered_config_hash(temp_workspace):
    create_approved_config(
        ws_dir=temp_workspace["ws_dir"],
        source_ids=[temp_workspace["source_id"]],
        tamper_hash=True,
    )
    builder = BuilderService(
        workspace_dir=temp_workspace["ws_dir"],
        ingestion_service=temp_workspace["ingestion"],
        recommendation_service=temp_workspace["rec_service"],
    )
    with pytest.raises(BuildGateError) as exc:
        builder.validate_preflight()
    assert "Configuration hash mismatch" in str(exc.value)


def test_gate_rejects_source_drift_added_or_missing(temp_workspace):
    create_approved_config(
        ws_dir=temp_workspace["ws_dir"],
        source_ids=[temp_workspace["source_id"], "nonexistent_src_999"],
    )
    builder = BuilderService(
        workspace_dir=temp_workspace["ws_dir"],
        ingestion_service=temp_workspace["ingestion"],
        recommendation_service=temp_workspace["rec_service"],
    )
    with pytest.raises(SourceDriftError) as exc:
        builder.validate_preflight()
    assert "Source drift detected" in str(exc.value)


def test_gate_rejects_source_disk_tampering(temp_workspace):
    create_approved_config(
        ws_dir=temp_workspace["ws_dir"],
        source_ids=[temp_workspace["source_id"]],
    )
    # Mutate disk content behind registry's back
    temp_workspace["doc_path"].write_text("Tampered file content! Breach detected.", encoding="utf-8")

    builder = BuilderService(
        workspace_dir=temp_workspace["ws_dir"],
        ingestion_service=temp_workspace["ingestion"],
        recommendation_service=temp_workspace["rec_service"],
    )
    with pytest.raises(SourceDriftError) as exc:
        builder.validate_preflight()
    assert "content modified on disk" in str(exc.value)


def test_gate_rejects_graph_rag_option_b(temp_workspace):
    create_approved_config(
        ws_dir=temp_workspace["ws_dir"],
        source_ids=[temp_workspace["source_id"]],
        arch_id=RagArchitectureId.GRAPH_RAG,
        chunk_strategy=ChunkingStrategyType.ENTITY_GRAPH,
    )
    builder = BuilderService(
        workspace_dir=temp_workspace["ws_dir"],
        ingestion_service=temp_workspace["ingestion"],
        recommendation_service=temp_workspace["rec_service"],
    )
    with pytest.raises(ArchitectureNotBuildableError) as exc:
        builder.validate_preflight()
    assert "Graph RAG indexing requires entity-relationship graph pipelines" in str(exc.value)


def test_gate_rejects_missing_model_no_fake_fallback(temp_workspace):
    # Tests that when a non-downloaded ONNX model is approved, preflight FAILS immediately
    # rather than silently substituting fake embeddings.
    create_approved_config(
        ws_dir=temp_workspace["ws_dir"],
        source_ids=[temp_workspace["source_id"]],
        embedding_provider="local_onnx",
        model_name="nonexistent-bge-model-q4",
    )
    builder = BuilderService(
        workspace_dir=temp_workspace["ws_dir"],
        ingestion_service=temp_workspace["ingestion"],
        recommendation_service=temp_workspace["rec_service"],
        # No test double override!
    )
    with pytest.raises(ModelNotAvailableError) as exc:
        builder.validate_preflight()
    assert "not found at" in str(exc.value) or "Model Manager" in str(exc.value)


def test_gate_rejects_concurrent_build_with_409(temp_workspace):
    create_approved_config(
        ws_dir=temp_workspace["ws_dir"],
        source_ids=[temp_workspace["source_id"]],
    )
    test_double = TestDeterministicEmbeddingProvider(dimension=384)
    builder = BuilderService(
        workspace_dir=temp_workspace["ws_dir"],
        ingestion_service=temp_workspace["ingestion"],
        recommendation_service=temp_workspace["rec_service"],
        embedding_provider_override=test_double,
    )

    build_id = builder.start_build()
    assert build_id.startswith("bld_")

    # Second concurrent start must raise BuildAlreadyRunningError
    with pytest.raises(BuildAlreadyRunningError) as exc:
        builder.start_build()
    assert "currently active" in str(exc.value)
    assert exc.value.active_build_id == build_id
