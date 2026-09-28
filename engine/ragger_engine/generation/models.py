"""
Canonical data models for Phase 7 Grounded Generation & Interactive RAG Chat Subsystem.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from ragger_engine.retrieval.models import RetrievalFilter


class GenerationState(str, Enum):
    IDLE = "idle"
    RETRIEVING = "retrieving"
    GENERATING = "generating"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class CitationValidationStatus(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED_DETECTED = "unverified_detected"
    NO_CITATIONS = "no_citations"


class ChatRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class MessageCitation(BaseModel):
    """Structured citation metadata derived strictly from verified RetrievedChunk provenance."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    source_name: str
    page_number: Optional[int] = None
    citation_text: str
    snippet: Optional[str] = None


class ChatMessage(BaseModel):
    """A single dialogue turn in an interactive chat session."""

    model_config = ConfigDict(extra="forbid")

    message_id: str
    role: ChatRole
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    valid_citations: List[MessageCitation] = Field(default_factory=list)
    unverified_citation_keys: List[str] = Field(default_factory=list)
    has_insufficient_evidence: bool = False


class ChatSession(BaseModel):
    """Persisted multi-turn chat session belonging to a specific workspace."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    workspace_id: str
    title: str
    messages: List[ChatMessage] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class GenerationConfig(BaseModel):
    """Application/workspace-managed generation parameters."""

    model_config = ConfigDict(extra="forbid")

    provider: str = "ollama"
    model_name: str = "llama3"
    temperature: float = Field(default=0.1, ge=0.0, le=1.0)
    max_tokens: int = Field(default=1024, ge=64, le=4096)


class ChatQueryRequest(BaseModel):
    """
    Restricted client request model.
    Client can NEVER supply a 'system' message or override the model name.
    """

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2000, description="The user question")
    session_id: Optional[str] = Field(default=None, description="Active session ID or None for new session")
    top_k: Optional[int] = Field(default=None, ge=1, le=50, description="Top-K passed through to Phase 6")
    filters: Optional[RetrievalFilter] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class GenerationResponse(BaseModel):
    """Complete synchronous generation response payload."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    message_id: str
    state: GenerationState = GenerationState.COMPLETED
    answer: str  # Original model-generated answer with [chk_...] intact
    valid_citations: List[MessageCitation]
    unverified_citation_keys: List[str]
    citation_validation_status: CitationValidationStatus
    retrieved_chunk_count: int
    has_insufficient_evidence: bool
    retrieval_latency_ms: float
    generation_latency_ms: float
    original_query: Optional[str] = None
    normalized_query: Optional[str] = None
    generation_provider: Optional[str] = None
    generation_model: Optional[str] = None
