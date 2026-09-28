"""
Validation and Cryptographic Hashing Utilities for Recommendation & Approval Lifecycle.
Enforces parameter validity, architecture compatibility, and Phase 5 build contracts.
"""

import hashlib
import json
from pathlib import Path
from typing import List, Optional, Tuple

from .exceptions import ArchitectureCompatibilityError, BuildNotApprovedError
from .models import (
    ApprovedBuildConfig,
    ChunkingConfig,
    ChunkingStrategyType,
    EmbeddingConfig,
    RagArchitectureId,
    RetrievalConfig,
    RetrievalStrategy,
    VectorDbConfig,
)


def compute_canonical_config_hash(
    architecture_id: RagArchitectureId,
    chunking_config: ChunkingConfig,
    embedding_config: EmbeddingConfig,
    vector_db_config: VectorDbConfig,
    retrieval_config: RetrievalConfig,
    source_ids: List[str],
) -> str:
    """
    Computes a deterministic SHA-256 digest of the canonical configuration.
    Guarantees that identical configuration payloads yield identical hash signatures.
    """
    canonical_payload = {
        "architecture_id": architecture_id.value,
        "chunking_config": chunking_config.model_dump(),
        "embedding_config": embedding_config.model_dump(),
        "retrieval_config": retrieval_config.model_dump(),
        "source_ids": sorted(list(set(source_ids))),
        "vector_db_config": vector_db_config.model_dump(),
    }
    raw_json = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw_json.encode("utf-8")).hexdigest()


def validate_architecture_compatibility(
    architecture_id: RagArchitectureId,
    chunking: ChunkingConfig,
    retrieval: RetrievalConfig,
) -> None:
    """
    Validates that chosen chunking and retrieval strategies are compatible with the target architecture.
    Prevents invalid parameter combinations (e.g. Hierarchical RAG with flat sliding chunking).
    """
    if architecture_id == RagArchitectureId.KNOWLEDGE_RAG:
        if chunking.strategy != ChunkingStrategyType.PARENT_CHILD_HIERARCHICAL:
            raise ArchitectureCompatibilityError(
                f"Knowledge RAG requires '{ChunkingStrategyType.PARENT_CHILD_HIERARCHICAL.value}' chunking, "
                f"got '{chunking.strategy.value}'."
            )
        if retrieval.strategy != RetrievalStrategy.PARENT_EXPANSION:
            raise ArchitectureCompatibilityError(
                f"Knowledge RAG requires '{RetrievalStrategy.PARENT_EXPANSION.value}' retrieval, "
                f"got '{retrieval.strategy.value}'."
            )

    elif architecture_id == RagArchitectureId.STRUCTURED_DATA_RAG:
        if chunking.strategy != ChunkingStrategyType.TABULAR_SCHEMA_SUMMARY:
            raise ArchitectureCompatibilityError(
                f"Structured Data RAG requires '{ChunkingStrategyType.TABULAR_SCHEMA_SUMMARY.value}' chunking, "
                f"got '{chunking.strategy.value}'."
            )
        if retrieval.strategy != RetrievalStrategy.DUAL_QUERY_ROUTE:
            raise ArchitectureCompatibilityError(
                f"Structured Data RAG requires '{RetrievalStrategy.DUAL_QUERY_ROUTE.value}' retrieval, "
                f"got '{retrieval.strategy.value}'."
            )

    elif architecture_id == RagArchitectureId.HYBRID_RAG:
        if retrieval.strategy != RetrievalStrategy.HYBRID_RRF:
            raise ArchitectureCompatibilityError(
                f"Hybrid RAG requires '{RetrievalStrategy.HYBRID_RRF.value}' retrieval, "
                f"got '{retrieval.strategy.value}'."
            )

    elif architecture_id == RagArchitectureId.RESEARCH_RAG:
        if chunking.strategy != ChunkingStrategyType.SECTION_AWARE:
            raise ArchitectureCompatibilityError(
                f"Research RAG requires '{ChunkingStrategyType.SECTION_AWARE.value}' chunking, "
                f"got '{chunking.strategy.value}'."
            )
        if retrieval.strategy != RetrievalStrategy.DENSE_SPARSE_RERANK:
            raise ArchitectureCompatibilityError(
                f"Research RAG requires '{RetrievalStrategy.DENSE_SPARSE_RERANK.value}' retrieval, "
                f"got '{retrieval.strategy.value}'."
            )

    elif architecture_id == RagArchitectureId.DOCUMENT_RAG:
        if chunking.strategy != ChunkingStrategyType.BOUNDARY_PARAGRAPH:
            raise ArchitectureCompatibilityError(
                f"Document RAG requires '{ChunkingStrategyType.BOUNDARY_PARAGRAPH.value}' chunking, "
                f"got '{chunking.strategy.value}'."
            )
        if retrieval.strategy != RetrievalStrategy.DENSE_VECTOR_TOP_K:
            raise ArchitectureCompatibilityError(
                f"Document RAG requires '{RetrievalStrategy.DENSE_VECTOR_TOP_K.value}' retrieval, "
                f"got '{retrieval.strategy.value}'."
            )

    elif architecture_id == RagArchitectureId.GRAPH_RAG:
        if chunking.strategy != ChunkingStrategyType.ENTITY_GRAPH:
            raise ArchitectureCompatibilityError(
                f"Graph RAG requires '{ChunkingStrategyType.ENTITY_GRAPH.value}' chunking, "
                f"got '{chunking.strategy.value}'."
            )
        if retrieval.strategy != RetrievalStrategy.GRAPH_TRAVERSAL:
            raise ArchitectureCompatibilityError(
                f"Graph RAG requires '{RetrievalStrategy.GRAPH_TRAVERSAL.value}' retrieval, "
                f"got '{retrieval.strategy.value}'."
            )


def validate_approved_build_config(
    config_path: Path,
    current_source_ids: Optional[List[str]] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Contract verification for Phase 5 RAG Builder.
    Verifies existence, frozen state, SHA-256 integrity, and source synchronization.
    """
    if not config_path.exists():
        return False, "BUILD_NOT_APPROVED: No approved_build_config.json snapshot found on disk."

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        config = ApprovedBuildConfig.model_validate(raw_data)
    except Exception as e:
        return False, f"BUILD_NOT_APPROVED: Corrupt or invalid configuration snapshot: {str(e)}"

    if not config.is_frozen:
        return False, "BUILD_NOT_APPROVED: Configuration is not marked as frozen."

    # Validate cryptographic hash
    expected_hash = compute_canonical_config_hash(
        architecture_id=config.approved_architecture,
        chunking_config=config.chunking_config,
        embedding_config=config.embedding_config,
        vector_db_config=config.vector_db_config,
        retrieval_config=config.retrieval_config,
        source_ids=config.source_ids,
    )
    if config.config_hash != expected_hash:
        return (
            False,
            f"BUILD_NOT_APPROVED: Hash mismatch detected. Stored: '{config.config_hash}', "
            f"Recomputed: '{expected_hash}'. Configuration snapshot was modified outside approved workflow.",
        )

    # Validate source IDs match current workspace if provided
    if current_source_ids is not None:
        if set(config.source_ids) != set(current_source_ids):
            return (
                False,
                f"BUILD_NOT_APPROVED: Source drift detected. Approved sources: {sorted(config.source_ids)}, "
                f"Current sources: {sorted(current_source_ids)}. Workspace changed since configuration approval.",
            )

    return True, None
