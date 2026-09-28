"""
Tests for Phase 5 End-to-End Build Pipeline, Atomic Activation, and Isolation.
Verifies all 5 buildable architectures, scratch build directory lifecycle,
manifest computation, retrieval sanity verification, cancellation cleanup,
and preservation of previous active builds.
"""

import json
import os
import shutil
import time
from pathlib import Path
import pytest

from ragger_engine.builder.embeddings.testing import TestDeterministicEmbeddingProvider
from ragger_engine.builder.models import BuildManifest, BuildStage
from ragger_engine.builder.service import BuilderService
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
def build_workspace(tmp_path: Path):
    ws_dir = tmp_path / "rag_workspace"
    ws_dir.mkdir(parents=True)
    sources_dir = ws_dir / "sources"
    sources_dir.mkdir(parents=True)

    registry = SourceRegistry(storage_dir=ws_dir)
    ingestion = IngestionService(registry=registry)
    rec_service = RecommendationService(storage_dir=ws_dir)

    yield {
        "ws_dir": ws_dir,
        "sources_dir": sources_dir,
        "registry": registry,
        "ingestion": ingestion,
        "rec_service": rec_service,
    }


def setup_build_config(
    ws_dir: Path,
    source_ids: list[str],
    arch_id: RagArchitectureId,
    chunk_strategy: ChunkingStrategyType,
    chunk_size: int = 256,
    chunk_overlap: int = 32,
) -> ApprovedBuildConfig:
    chunking = ChunkingConfig(
        strategy=chunk_strategy,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    embedding = EmbeddingConfig(
        provider="local_onnx",
        model_name="bge-small-en-v1.5",
        dimension=384,
    )
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

    config = ApprovedBuildConfig(
        config_id=f"cfg_{arch_id.value}",
        config_version=1,
        config_hash=canonical_hash,
        workspace_id=ws_dir.name,
        recommended_architecture=arch_id,
        approved_architecture=arch_id,
        user_customized=False,
        source_ids=source_ids,
        chunking_config=chunking,
        embedding_config=embedding,
        vector_db_config=vector_db,
        retrieval_config=retrieval,
        is_frozen=True,
    )
    with open(ws_dir / "approved_build_config.json", "w", encoding="utf-8") as f:
        f.write(config.model_dump_json(indent=2))
    return config


# ---------------------------------------------------------------------------
# Test 1: All 5 Buildable Architectures
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "arch_id,strategy,filename,content",
    [
        (
            RagArchitectureId.DOCUMENT_RAG,
            ChunkingStrategyType.BOUNDARY_PARAGRAPH,
            "handbook.txt",
            "Section 1: General Policy.\nEmployees must submit reports on Friday.\n\nSection 2: Travel Expenses.\nReceipts must be itemized.",
        ),
        (
            RagArchitectureId.KNOWLEDGE_RAG,
            ChunkingStrategyType.PARENT_CHILD_HIERARCHICAL,
            "architecture_guide.txt",
            "Overview of the Distributed Architecture.\nThis document covers microservices and state synchronization.\n"
            * 5,
        ),
        (
            RagArchitectureId.STRUCTURED_DATA_RAG,
            ChunkingStrategyType.TABULAR_SCHEMA_SUMMARY,
            "sales.csv",
            "Order_ID,Customer_Name,Revenue,Region\n101,Acme Corp,5000,US-West\n102,Beta LLC,3200,EU-Central\n103,Gamma Inc,8100,APAC",
        ),
        (
            RagArchitectureId.RESEARCH_RAG,
            ChunkingStrategyType.SECTION_AWARE,
            "paper.md",
            "# Abstract\nWe evaluate neural retrieval methods.\n\n# Methodology\nWe apply dual-encoder embeddings on technical corpora.\n\n# Results\nPrecision increased by 14.2% across benchmarks.",
        ),
    ],
)
def test_pipeline_builds_individual_architectures(build_workspace, arch_id, strategy, filename, content):
    """Verifies that Document, Knowledge, Structured Data, and Research RAG all build successfully."""
    sources_dir = build_workspace["sources_dir"]
    file_path = sources_dir / filename
    file_path.write_text(content, encoding="utf-8")

    result = build_workspace["ingestion"].ingest(str(file_path))
    source_id = result.source.source_id

    setup_build_config(
        ws_dir=build_workspace["ws_dir"],
        source_ids=[source_id],
        arch_id=arch_id,
        chunk_strategy=strategy,
    )

    test_embedding = TestDeterministicEmbeddingProvider(dimension=384)
    builder = BuilderService(
        workspace_dir=build_workspace["ws_dir"],
        ingestion_service=build_workspace["ingestion"],
        recommendation_service=build_workspace["rec_service"],
        embedding_provider_override=test_embedding,
    )

    build_id = builder.start_build()
    assert build_id.startswith("bld_")

    done = builder.wait_for_completion(timeout=10.0)
    assert done, "Build did not complete within timeout"

    progress = builder.progress
    assert progress.status == "completed"
    assert progress.current_stage == BuildStage.COMPLETED
    assert progress.chunks_processed > 0
    assert progress.vectors_processed == progress.chunks_processed

    # Verify active build manifest
    manifest = builder.get_active_manifest()
    assert manifest is not None
    assert manifest.build_id == build_id
    assert manifest.approved_architecture == arch_id.value
    assert manifest.chunk_count == progress.chunks_processed
    assert manifest.vector_count == progress.vectors_processed

    # Verify scratch was cleaned up and immutable build directory created
    scratch_dir = build_workspace["ws_dir"] / "builds" / f"{build_id}_scratch"
    build_dir = build_workspace["ws_dir"] / "builds" / build_id
    assert not scratch_dir.exists()
    assert build_dir.exists()
    assert (build_dir / "manifest.json").exists()
    assert (build_dir / "index" / "chunks.jsonl").exists()
    assert (build_dir / "index" / "vectors.json").exists()
    assert (build_dir / "index" / "index_meta.json").exists()


def test_pipeline_builds_hybrid_rag_multi_modal(build_workspace):
    """
    Verifies Hybrid RAG builds with both DocumentModel (prose) and DatasetModel (tabular)
    preserving their distinct chunking dispatch.
    """
    sources_dir = build_workspace["sources_dir"]

    # 1. Prose file
    doc_path = sources_dir / "quarterly_narrative.txt"
    doc_path.write_text("Q3 Earnings Report.\nTotal revenue increased significantly due to enterprise expansion.", encoding="utf-8")
    res_doc = build_workspace["ingestion"].ingest(str(doc_path))

    # 2. Table file
    table_path = sources_dir / "financial_metrics.csv"
    table_path.write_text("Metric,Q2,Q3\nOperating_Margin,18%,22%\nNet_Income,1.2M,1.8M", encoding="utf-8")
    res_table = build_workspace["ingestion"].ingest(str(table_path))

    setup_build_config(
        ws_dir=build_workspace["ws_dir"],
        source_ids=[res_doc.source.source_id, res_table.source.source_id],
        arch_id=RagArchitectureId.HYBRID_RAG,
        chunk_strategy=ChunkingStrategyType.BOUNDARY_PARAGRAPH,
    )

    test_embedding = TestDeterministicEmbeddingProvider(dimension=384)
    builder = BuilderService(
        workspace_dir=build_workspace["ws_dir"],
        ingestion_service=build_workspace["ingestion"],
        recommendation_service=build_workspace["rec_service"],
        embedding_provider_override=test_embedding,
    )

    build_id = builder.start_build()
    done = builder.wait_for_completion(timeout=10.0)
    assert done

    progress = builder.progress
    assert progress.status == "completed"
    assert progress.chunks_processed >= 2  # At least 1 prose chunk + 1 table schema/row chunk

    manifest = builder.get_active_manifest()
    assert manifest is not None
    assert manifest.approved_architecture == "hybrid_rag"
    assert len(manifest.source_ids) == 2


# ---------------------------------------------------------------------------
# Test 2: Atomic Activation & Manifest Integrity
# ---------------------------------------------------------------------------

def test_atomic_activation_and_manifest_hash_integrity(build_workspace):
    """
    Verifies that the manifest hash computed by BuilderService matches
    the independent canonical hash calculation and active_build.json is atomic.
    """
    sources_dir = build_workspace["sources_dir"]
    doc_path = sources_dir / "data.txt"
    doc_path.write_text("Security guidelines and compliance checklist.", encoding="utf-8")
    res = build_workspace["ingestion"].ingest(str(doc_path))

    setup_build_config(
        ws_dir=build_workspace["ws_dir"],
        source_ids=[res.source.source_id],
        arch_id=RagArchitectureId.DOCUMENT_RAG,
        chunk_strategy=ChunkingStrategyType.BOUNDARY_PARAGRAPH,
    )

    test_embedding = TestDeterministicEmbeddingProvider(dimension=384)
    builder = BuilderService(
        workspace_dir=build_workspace["ws_dir"],
        ingestion_service=build_workspace["ingestion"],
        recommendation_service=build_workspace["rec_service"],
        embedding_provider_override=test_embedding,
    )

    build_id = builder.start_build()
    builder.wait_for_completion(timeout=10.0)

    # Verify active_build.json
    pointer_path = build_workspace["ws_dir"] / "active_build.json"
    assert pointer_path.exists()
    with open(pointer_path, "r", encoding="utf-8") as f:
        pointer = json.load(f)
    assert pointer["active_build_id"] == build_id

    # Verify manifest hash recalculation
    manifest = builder.get_active_manifest()
    assert manifest is not None
    manifest_data = manifest.model_dump()
    expected_hash = BuildManifest.compute_manifest_hash(manifest_data)
    assert manifest.manifest_hash == expected_hash


# ---------------------------------------------------------------------------
# Test 3: Cancellation Safety & Scratch Directory Cleanup
# ---------------------------------------------------------------------------

def test_cancellation_cleans_scratch_and_leaves_prior_build(build_workspace):
    """
    1. Complete Build 1 -> Active
    2. Start Build 2 -> Immediately request cancellation
    3. Verify Build 2 scratch directory is purged
    4. Verify Build 1 remains the active build untouched
    """
    sources_dir = build_workspace["sources_dir"]
    doc_path = sources_dir / "notes.txt"
    doc_path.write_text("Version 1 persistent notes.", encoding="utf-8")
    res = build_workspace["ingestion"].ingest(str(doc_path))

    setup_build_config(
        ws_dir=build_workspace["ws_dir"],
        source_ids=[res.source.source_id],
        arch_id=RagArchitectureId.DOCUMENT_RAG,
        chunk_strategy=ChunkingStrategyType.BOUNDARY_PARAGRAPH,
    )

    test_embedding = TestDeterministicEmbeddingProvider(dimension=384)
    builder = BuilderService(
        workspace_dir=build_workspace["ws_dir"],
        ingestion_service=build_workspace["ingestion"],
        recommendation_service=build_workspace["rec_service"],
        embedding_provider_override=test_embedding,
    )

    # 1. Complete initial build
    build_1_id = builder.start_build()
    builder.wait_for_completion(timeout=10.0)
    assert builder.progress.status == "completed"

    manifest_1 = builder.get_active_manifest()
    assert manifest_1.build_id == build_1_id

    # 2. Start Build 2 with delayed embedding to catch cancellation
    class SlowEmbeddingProvider(TestDeterministicEmbeddingProvider):
        def embed_batch(self, texts):
            time.sleep(0.3)
            return super().embed_batch(texts)

    slow_embedding = SlowEmbeddingProvider(dimension=384)
    builder._embedding_provider_override = slow_embedding

    build_2_id = builder.start_build()
    # Request cancellation immediately
    builder.cancel_build(build_2_id)
    builder.wait_for_completion(timeout=10.0)

    progress = builder.progress
    assert progress.status in ("cancelled", "cancel_requested")

    # 3. Scratch directory for build 2 must be purged
    scratch_2 = build_workspace["ws_dir"] / "builds" / f"{build_2_id}_scratch"
    assert not scratch_2.exists()

    # 4. Build 1 remains intact as active build
    active_manifest = builder.get_active_manifest()
    assert active_manifest is not None
    assert active_manifest.build_id == build_1_id
    assert (build_workspace["ws_dir"] / "builds" / build_1_id / "manifest.json").exists()


# ---------------------------------------------------------------------------
# Test 4: Pre-activation Source Drift Revalidation
# ---------------------------------------------------------------------------

def test_pre_activation_source_drift_aborts_and_cleans_scratch(build_workspace):
    """
    Simulates a race condition where source content on disk is modified
    during embedding/indexing.
    The pre-activation check must detect the drift, abort before pointer swap,
    and delete the scratch directory.
    """
    sources_dir = build_workspace["sources_dir"]
    doc_path = sources_dir / "contract.txt"
    doc_path.write_text("Standard mutual non-disclosure agreement.", encoding="utf-8")
    res = build_workspace["ingestion"].ingest(str(doc_path))

    setup_build_config(
        ws_dir=build_workspace["ws_dir"],
        source_ids=[res.source.source_id],
        arch_id=RagArchitectureId.DOCUMENT_RAG,
        chunk_strategy=ChunkingStrategyType.BOUNDARY_PARAGRAPH,
    )

    class TamperingEmbeddingProvider(TestDeterministicEmbeddingProvider):
        def embed_batch(self, texts):
            # Mutate the file on disk during embedding!
            doc_path.write_text("MALICIOUS CONTENT INJECTED DURING BUILD!", encoding="utf-8")
            return super().embed_batch(texts)

    tamper_embedding = TamperingEmbeddingProvider(dimension=384)
    builder = BuilderService(
        workspace_dir=build_workspace["ws_dir"],
        ingestion_service=build_workspace["ingestion"],
        recommendation_service=build_workspace["rec_service"],
        embedding_provider_override=tamper_embedding,
    )

    build_id = builder.start_build()
    builder.wait_for_completion(timeout=10.0)

    progress = builder.progress
    assert progress.status == "failed"
    assert progress.current_stage == BuildStage.FAILED
    assert "SOURCE_DRIFT" in (progress.error_code or "") or "Source integrity broken" in (progress.message or "")

    # Scratch directory must be cleaned up
    scratch_dir = build_workspace["ws_dir"] / "builds" / f"{build_id}_scratch"
    assert not scratch_dir.exists()

    # Active pointer must not exist
    assert not (build_workspace["ws_dir"] / "active_build.json").exists()
