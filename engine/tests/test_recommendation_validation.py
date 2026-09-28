"""
Tests for parameter validation and architecture compatibility in Recommendation Engine.
"""

import pytest
from pydantic import ValidationError
from ragger_engine.recommendation.exceptions import ArchitectureCompatibilityError
from ragger_engine.recommendation.models import (
    ChunkingConfig,
    ChunkingStrategyType,
    RagArchitectureId,
    RetrievalConfig,
    RetrievalStrategy,
)
from ragger_engine.recommendation.validation import validate_architecture_compatibility


def test_chunking_config_overlap_must_be_strictly_less_than_chunk_size():
    # overlap == chunk_size
    with pytest.raises(ValidationError) as exc:
        ChunkingConfig(
            strategy=ChunkingStrategyType.BOUNDARY_PARAGRAPH,
            chunk_size=256,
            chunk_overlap=256,
        )
    assert "chunk_overlap (256) must be strictly less than chunk_size (256)" in str(exc.value)

    # overlap > chunk_size
    with pytest.raises(ValidationError):
        ChunkingConfig(
            strategy=ChunkingStrategyType.BOUNDARY_PARAGRAPH,
            chunk_size=256,
            chunk_overlap=300,
        )


def test_hierarchical_chunking_child_must_be_less_than_parent():
    with pytest.raises(ValidationError) as exc:
        ChunkingConfig(
            strategy=ChunkingStrategyType.PARENT_CHILD_HIERARCHICAL,
            chunk_size=512,
            chunk_overlap=64,
            child_chunk_size=512,
            parent_chunk_size=256,
        )
    assert "child_chunk_size (512) must be strictly less than parent_chunk_size (256)" in str(exc.value)


def test_retrieval_config_top_k_bounds():
    with pytest.raises(ValidationError):
        RetrievalConfig(
            strategy=RetrievalStrategy.DENSE_VECTOR_TOP_K,
            top_k=0,
        )


def test_architecture_compatibility_knowledge_rag():
    valid_chunking = ChunkingConfig(
        strategy=ChunkingStrategyType.PARENT_CHILD_HIERARCHICAL,
        chunk_size=512,
        chunk_overlap=64,
        child_chunk_size=192,
        parent_chunk_size=768,
    )
    valid_retrieval = RetrievalConfig(
        strategy=RetrievalStrategy.PARENT_EXPANSION,
        top_k=5,
    )

    # Valid combination should not raise
    validate_architecture_compatibility(RagArchitectureId.KNOWLEDGE_RAG, valid_chunking, valid_retrieval)

    # Incompatible chunking
    invalid_chunking = ChunkingConfig(
        strategy=ChunkingStrategyType.BOUNDARY_PARAGRAPH,
        chunk_size=512,
        chunk_overlap=64,
    )
    with pytest.raises(ArchitectureCompatibilityError) as exc:
        validate_architecture_compatibility(RagArchitectureId.KNOWLEDGE_RAG, invalid_chunking, valid_retrieval)
    assert "Knowledge RAG requires 'parent_child_hierarchical'" in str(exc.value)


def test_architecture_compatibility_hybrid_rag():
    valid_chunking = ChunkingConfig(
        strategy=ChunkingStrategyType.BOUNDARY_PARAGRAPH,
        chunk_size=512,
        chunk_overlap=64,
    )
    valid_retrieval = RetrievalConfig(
        strategy=RetrievalStrategy.HYBRID_RRF,
        top_k=5,
        rrf_k=60,
    )

    validate_architecture_compatibility(RagArchitectureId.HYBRID_RAG, valid_chunking, valid_retrieval)

    invalid_retrieval = RetrievalConfig(
        strategy=RetrievalStrategy.DENSE_VECTOR_TOP_K,
        top_k=5,
    )
    with pytest.raises(ArchitectureCompatibilityError) as exc:
        validate_architecture_compatibility(RagArchitectureId.HYBRID_RAG, valid_chunking, invalid_retrieval)
    assert "Hybrid RAG requires 'hybrid_rrf'" in str(exc.value)
