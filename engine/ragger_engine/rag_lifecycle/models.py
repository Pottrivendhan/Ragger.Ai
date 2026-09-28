"""
Data models for Phase 12 RAG Artifact Lifecycle & Storage Contract.
Decoupled completely from LLM runtimes, models, and generation providers.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Union
import uuid
from pydantic import BaseModel, Field


class RAGStatus(str, Enum):
    ACTIVE = "active"
    DRAFT = "draft"
    ARCHIVED = "archived"


class RAGVersionInfo(BaseModel):
    """Represents a specific compiled version/build of a RAG artifact."""
    version_id: str
    version_tag: str
    build_id: str
    created_at: Union[str, datetime]
    chunk_count: int = 0
    vector_count: int = 0
    manifest_hash: str
    manifest_id: Optional[str] = None
    embedding_model: Optional[str] = None
    vector_store: Optional[str] = None


class RAGArtifactRecord(BaseModel):
    """
    First-class RAG knowledge artifact.
    Identified by an immutable rag_id.
    Contains versions mapping to builds, with an active_version_id pointer.
    """
    rag_id: str
    name: str
    description: str = ""
    status: RAGStatus = RAGStatus.ACTIVE
    active_version_id: Optional[str] = None
    versions: List[RAGVersionInfo] = Field(default_factory=list)
    source_ids: List[str] = Field(default_factory=list)
    account_id: str = "acc_default"
    created_at: Union[str, datetime] = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: Union[str, datetime] = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class RAGPackFileHash(BaseModel):
    sha256: str
    size_bytes: int


class RAGPackManifest(BaseModel):
    """Deterministic manifest embedded inside a .ragpack ZIP bundle."""
    schema_version: str = "1.0"
    rag_id: str
    rag_name: str
    version_id: str
    version_tag: str
    build_id: str
    files: Dict[str, RAGPackFileHash]
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CreateRAGRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    initial_build_id: Optional[str] = None
    account_id: Optional[str] = "acc_default"


class UpdateRAGRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[RAGStatus] = None
    active_version_id: Optional[str] = None


class RegisterVersionRequest(BaseModel):
    build_id: str
    version_tag: str
    set_active: bool = True


class VersionComparisonSummary(BaseModel):
    chunk_count: int
    vector_count: int
    sources_count: int
    manifest_hash: str
    embedding_model: Optional[str] = None
    vector_store: Optional[str] = None
    architecture: Optional[str] = None


class VersionComparisonResult(BaseModel):
    """
    Descriptive comparison between two RAG versions.
    Purely objective and factual metrics without qualitative judgments.
    """
    rag_id: str
    base_version_id: str
    base_version_tag: str
    target_version_id: str
    target_version_tag: str
    base: VersionComparisonSummary
    target: VersionComparisonSummary
    chunk_count_delta: int
    vector_count_delta: int
    sources_count_delta: int
    manifest_hash_changed: bool
    embedding_model_changed: bool
    sources_added: List[str]
    sources_removed: List[str]
    sources_retained: List[str]


class RAGSuggestionsResponse(BaseModel):
    rag_id: str
    suggestions: List[str]

