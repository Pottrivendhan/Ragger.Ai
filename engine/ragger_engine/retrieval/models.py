"""
Canonical Pydantic Schemas for Phase 6 RAG Retrieval Subsystem.
Strict validation with extra='forbid' to preserve data integrity across retrieval boundaries.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from ragger_engine.builder.models import ChunkType


class ScoreType(str, Enum):
    """Classification of ranking score to ensure unambiguous presentation in UI."""

    COSINE_SIMILARITY = "cosine_similarity"
    RRF = "rrf"
    LEXICAL_DENSE = "lexical_dense"
    STRUCTURED_MATCH = "structured_match"


class RetrievalFilter(BaseModel):
    """Strongly-typed query filters preventing arbitrary structure injection."""

    model_config = ConfigDict(extra="forbid")

    source_ids: Optional[List[str]] = Field(default=None, description="Restrict retrieval to specific source IDs")
    source_name: Optional[str] = Field(default=None, description="Filter by exact source filename")
    page_numbers: Optional[List[int]] = Field(default=None, description="Restrict retrieval to specific page numbers")
    chunk_types: Optional[List[ChunkType]] = Field(default=None, description="Filter by specific chunk types")
    heading_contains: Optional[str] = Field(default=None, description="Filter chunks whose heading path contains this substring")


class RetrievalQuery(BaseModel):
    """Incoming user search request."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2000, description="The user question or search phrase")
    top_k: Optional[int] = Field(default=None, ge=1, le=50, description="Override retrieval count within approved limits")
    filters: Optional[RetrievalFilter] = None


class CitationProvenance(BaseModel):
    """Authoritative raw provenance metadata for auditing citations."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_name: str
    source_sha256: str
    chunk_id: str
    chunk_type: ChunkType
    page_number: Optional[int] = None
    paragraph_index: Optional[int] = None
    heading_path: List[str] = Field(default_factory=list)
    token_count: int


class RetrievedChunk(BaseModel):
    """Grounded retrieval candidate returned to consumer."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    text: str
    score: float
    score_type: ScoreType
    provenance: CitationProvenance
    parent_chunk_id: Optional[str] = None
    parent_text: Optional[str] = None
    matched_child_snippets: List[str] = Field(default_factory=list)
    citation: str


class RetrievalResponse(BaseModel):
    """Complete retrieval payload including grounded context prompt."""

    model_config = ConfigDict(extra="forbid")

    query: str
    architecture: str
    strategy: str
    results: List[RetrievedChunk]
    total_candidates: int
    latency_ms: float
    manifest_id: str
    manifest_hash: str
    grounded_context_prompt: str


class RetrievalStatus(BaseModel):
    """Authoritative diagnostic status of the retrieval engine and active build."""

    model_config = ConfigDict(extra="forbid")

    has_active_build: bool
    active_build_id: Optional[str] = None
    manifest_id: Optional[str] = None
    manifest_hash: Optional[str] = None
    approved_architecture: Optional[str] = None
    chunk_count: int = 0
    vector_count: int = 0
    embedding_model: Optional[str] = None
    vector_store: Optional[str] = None
    retrieval_strategy: Optional[str] = None
