"""
Canonical Pydantic models for the Phase 4 Deterministic Recommendation Engine.
Defines architectures, parameter configurations, rule results, and frozen build snapshots.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class RagArchitectureId(str, Enum):
    DOCUMENT_RAG = "document_rag"
    KNOWLEDGE_RAG = "knowledge_rag"
    STRUCTURED_DATA_RAG = "structured_data_rag"
    HYBRID_RAG = "hybrid_rag"
    RESEARCH_RAG = "research_rag"
    GRAPH_RAG = "graph_rag"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RetrievalStrategy(str, Enum):
    DENSE_VECTOR_TOP_K = "dense_vector_top_k"
    PARENT_EXPANSION = "parent_expansion"
    DUAL_QUERY_ROUTE = "dual_query_route"
    HYBRID_RRF = "hybrid_rrf"
    DENSE_SPARSE_RERANK = "dense_sparse_rerank"
    GRAPH_TRAVERSAL = "graph_traversal"


class ChunkingStrategyType(str, Enum):
    BOUNDARY_PARAGRAPH = "boundary_paragraph"
    PARENT_CHILD_HIERARCHICAL = "parent_child_hierarchical"
    TABULAR_SCHEMA_SUMMARY = "tabular_schema_summary"
    SECTION_AWARE = "section_aware"
    ENTITY_GRAPH = "entity_graph"


class ChunkingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: ChunkingStrategyType
    chunk_size: int = Field(default=512, ge=64, le=4096)
    chunk_overlap: int = Field(default=64, ge=0)
    child_chunk_size: Optional[int] = Field(default=None, ge=32, le=1024)
    parent_chunk_size: Optional[int] = Field(default=None, ge=128, le=4096)

    @model_validator(mode="after")
    def validate_overlap_and_hierarchy(self) -> "ChunkingConfig":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(f"chunk_overlap ({self.chunk_overlap}) must be strictly less than chunk_size ({self.chunk_size}).")

        if self.strategy == ChunkingStrategyType.PARENT_CHILD_HIERARCHICAL:
            child = self.child_chunk_size or 192
            parent = self.parent_chunk_size or 768
            if child >= parent:
                raise ValueError(f"child_chunk_size ({child}) must be strictly less than parent_chunk_size ({parent}).")
            self.child_chunk_size = child
            self.parent_chunk_size = parent
        return self


class EmbeddingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(default="local_onnx", min_length=1)
    model_name: str = Field(default="bge-small-en-v1.5", min_length=1)
    dimension: int = Field(default=384, ge=64, le=4096)


class VectorDbConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(default="lancedb", min_length=1)
    metric: str = Field(default="cosine", min_length=1)
    index_type: str = Field(default="auto", min_length=1)


class RetrievalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: RetrievalStrategy
    top_k: int = Field(default=5, ge=1, le=50)
    rerank_enabled: bool = False
    rrf_k: Optional[int] = Field(default=None, ge=1, le=200)

    @model_validator(mode="after")
    def validate_rrf_k(self) -> "RetrievalConfig":
        if self.strategy == RetrievalStrategy.HYBRID_RRF:
            if self.rrf_k is None:
                self.rrf_k = 60
        return self


class ArchitectureSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    architecture_id: RagArchitectureId
    title: str
    tagline: str
    why_recommended: str
    strengths: List[str]
    tradeoffs: List[str]
    alternative_options: List[RagArchitectureId]
    default_chunking: ChunkingConfig
    default_embedding: EmbeddingConfig
    default_vector_db: VectorDbConfig
    default_retrieval: RetrievalConfig


class RuleEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    matched: bool
    confidence_score: float = Field(ge=0.0, le=1.0)
    detected_signals: List[str]
    target_architecture: RagArchitectureId


class RecommendationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation_id: str
    recommended_architecture: RagArchitectureId
    architecture_spec: ArchitectureSpec
    confidence_score: float = Field(ge=0.0, le=1.0)
    confidence_level: ConfidenceLevel
    matched_rule_id: str
    detected_signals: List[str]
    alternative_architectures: List[ArchitectureSpec]
    evaluated_rules: List[RuleEvaluationResult]
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ApprovedBuildConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_id: str
    config_version: int = Field(default=1, ge=1)
    config_hash: str
    created_from_recommendation_id: Optional[str] = None
    workspace_id: str = "default"
    recommended_architecture: RagArchitectureId
    approved_architecture: RagArchitectureId
    user_customized: bool = False
    source_ids: List[str]
    chunking_config: ChunkingConfig
    embedding_config: EmbeddingConfig
    vector_db_config: VectorDbConfig
    retrieval_config: RetrievalConfig
    approved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_frozen: bool = True
