"""
Models for Phase 16 Multi-RAG Hybrid Synthesis and Multi-Attachment Agents.
Enforces strict provenance, internal build_id encapsulation, and composite chunk identity.
"""

from typing import List, Optional
from pydantic import BaseModel, Field
from ragger_engine.retrieval.models import RetrievalResponse


class ResolvedRAGTarget(BaseModel):
    """
    Internal server-authoritative resolution target.
    Authoritative resolution chain:
    rag_id -> active_version_id -> RAGVersion -> build_id -> BuildRuntimeCache[build_id]
    
    CRITICAL: build_id is strictly backend-internal and must never be exposed to the client.
    """
    rag_id: str
    rag_name: str
    version_id: str
    version_tag: str
    build_id: str


class MultiRAGClientTarget(BaseModel):
    """
    Client-facing projection of resolved RAG target.
    Purposely excludes build_id to ensure client remains unaware of internal runtime build selection.
    """
    rag_id: str
    rag_name: str
    version_id: str
    version_tag: str


class MultiRAGRetrievalResult(BaseModel):
    """
    Strongly couples retrieval response with the exact target build that produced it.
    Prevents loss of provenance even if active version subsequently mutates.
    """
    target: ResolvedRAGTarget
    response: RetrievalResponse


class MultiRAGCandidate(BaseModel):
    """
    Candidate chunk retrieved from a specific RAG artifact build.
    Composite identity is strictly: rag_id + build_id + chunk_id.
    """
    rag_id: str
    rag_name: str
    version_id: str
    version_tag: str
    build_id: str
    chunk_id: str
    source_id: str
    source_name: str
    page_number: Optional[int] = None
    heading_path: List[str] = Field(default_factory=list)
    text: str
    raw_score: float = 0.0
    retrieval_rank: int = 1  # 1-indexed rank within originating RAG
    rrf_score: float = 0.0   # Global Reciprocal Rank Fusion score

    @property
    def composite_key(self) -> str:
        """Authoritative composite identity preventing collisions across RAGs."""
        return f"{self.rag_id}:{self.build_id}:{self.chunk_id}"


class MultiRAGFusedContext(BaseModel):
    """
    Fused candidate context produced by Reciprocal Rank Fusion and deduplication.
    """
    candidates: List[MultiRAGCandidate]
    targets_resolved: List[ResolvedRAGTarget]
    total_candidates: int
    retrieval_latency_ms: float = 0.0
