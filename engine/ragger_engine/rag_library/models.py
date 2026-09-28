"""
Read-only data models for RAG Library knowledge artifacts.
Strictly decoupled from LLM runtimes and generation providers.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class RAGSourceSummary(BaseModel):
    """Metadata summary of a source file indexed in a RAG artifact."""
    source_id: str
    filename: str
    detected_format: Optional[str] = None
    file_size_bytes: Optional[int] = None
    sha256_checksum: Optional[str] = None


class RAGSampleChunk(BaseModel):
    """A sample text chunk from the RAG artifact for non-LLM inspection."""
    chunk_id: str
    source_name: str
    page_number: Optional[int] = None
    snippet: str


class RAGArtifact(BaseModel):
    """
    Representation of a completed, immutable RAG knowledge artifact.
    Contains vector store index references, chunk counts, and source provenance.
    """
    rag_id: str
    build_id: str
    manifest_id: str
    manifest_hash: str
    status: str
    approved_architecture: str
    chunk_count: int
    vector_count: int
    embedding_dimension: int
    embedding_model: str
    vector_store: str
    started_at: Optional[Union[str, datetime]] = None
    completed_at: Optional[Union[str, datetime]] = None
    build_duration_ms: Optional[float] = None
    is_active: bool = False
    sources: List[RAGSourceSummary] = Field(default_factory=list)


class RAGArtifactDetail(RAGArtifact):
    """Detailed inspection model including chunking/retrieval config and sample chunks."""
    chunking_config: Dict[str, Any] = Field(default_factory=dict)
    retrieval_config: Dict[str, Any] = Field(default_factory=dict)
    sample_chunks: List[RAGSampleChunk] = Field(default_factory=list)
