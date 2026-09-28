"""
Data models for Phase 11B Agent Workspace Foundation.
Strictly separates Agent configuration and state from underlying RAG knowledge builds and LLM runtimes.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from ragger_engine.retrieval.models import RetrievalFilter


class GroundingPolicy(str, Enum):
    """Grounding constraint level enforced on agent answers."""
    STRICT_GROUNDED = "strict_grounded"      # Standard: 0-citation fail closed on OOD
    CONVERSATIONAL_STRICT = "conversational_strict" # Multi-turn coherence, strictly grounded facts


class AgentProfile(BaseModel):
    """
    Independent Agent configuration.
    Stores metadata, persona directive, attached RAG artifact references, and runtime reference.
    Does NOT duplicate RAG indices, vectors, chunks, or model weights.
    """
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    system_prompt: Optional[str] = Field(default=None, max_length=2000)
    grounding_policy: GroundingPolicy = GroundingPolicy.STRICT_GROUNDED
    attached_rag_ids: List[str] = Field(default_factory=list)
    runtime_ref: Optional[str] = Field(default="local_gguf")
    account_id: str = "acc_default"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CreateAgentRequest(BaseModel):
    """Payload to create a new Agent."""
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    system_prompt: Optional[str] = Field(default=None, max_length=2000)
    grounding_policy: Optional[GroundingPolicy] = GroundingPolicy.STRICT_GROUNDED
    attached_rag_ids: Optional[List[str]] = Field(default_factory=list)
    runtime_ref: Optional[str] = Field(default="local_gguf")
    account_id: Optional[str] = "acc_default"


class UpdateAgentRequest(BaseModel):
    """Payload to update an existing Agent."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    system_prompt: Optional[str] = Field(default=None, max_length=2000)
    grounding_policy: Optional[GroundingPolicy] = None
    attached_rag_ids: Optional[List[str]] = None
    runtime_ref: Optional[str] = None


class AttachRAGRequest(BaseModel):
    """Payload to attach a RAG knowledge artifact to an agent."""
    rag_id: str = Field(min_length=1, description="RAG Artifact ID (e.g. rag_bld_6f509ca2)")


class AgentCitation(BaseModel):
    """
    Full provenance citation identifying the originating RAG knowledge artifact and build.
    Prevents ambiguity across multiple attached RAGs.
    """
    rag_id: str
    build_id: str
    source_id: str
    source_name: str
    chunk_id: str
    page_number: Optional[int] = None
    citation_text: str
    snippet: Optional[str] = None


class AgentChatRequest(BaseModel):
    """Chat invocation request directed to an Agent."""
    query: str = Field(min_length=1, max_length=2000)
    session_id: Optional[str] = Field(default=None)
    top_k: Optional[int] = Field(default=None, ge=1, le=50)
    filters: Optional[RetrievalFilter] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class AgentChatResponse(BaseModel):
    """Response returned from Agent Chat through the verified core engine."""
    agent_id: str
    session_id: str
    message_id: str
    answer: str
    citations: List[AgentCitation] = Field(default_factory=list)
    retrieved_chunk_count: int
    has_insufficient_evidence: bool
    retrieval_latency_ms: float
    generation_latency_ms: float
    original_query: Optional[str] = None
    normalized_query: Optional[str] = None
    generation_provider: Optional[str] = None
    generation_model: Optional[str] = None
