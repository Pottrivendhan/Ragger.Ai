"""
Agent Workspace Subsystem.
Provides agent profiles, decoupled RAG attachments, and chat orchestration.
"""

from ragger_engine.agent_workspace.exceptions import (
    AgentNotFoundError,
    AgentWorkspaceError,
    NoAttachedRAGError,
    RAGArtifactNotFoundError,
)
from ragger_engine.agent_workspace.models import (
    AgentChatRequest,
    AgentChatResponse,
    AgentCitation,
    AgentProfile,
    AttachRAGRequest,
    CreateAgentRequest,
    GroundingPolicy,
    UpdateAgentRequest,
)
from ragger_engine.agent_workspace.service import AgentWorkspaceService

__all__ = [
    "AgentProfile",
    "CreateAgentRequest",
    "UpdateAgentRequest",
    "AttachRAGRequest",
    "AgentChatRequest",
    "AgentChatResponse",
    "AgentCitation",
    "GroundingPolicy",
    "AgentWorkspaceError",
    "AgentNotFoundError",
    "RAGArtifactNotFoundError",
    "NoAttachedRAGError",
    "AgentWorkspaceService",
]
