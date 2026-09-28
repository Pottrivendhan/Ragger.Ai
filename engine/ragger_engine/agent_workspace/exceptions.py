"""
Service exceptions for Agent Workspace layer.
"""

from typing import Any, Dict, Optional


class AgentWorkspaceError(Exception):
    """Base exception for agent workspace operations."""
    def __init__(self, message: str, code: str = "AGENT_ERROR", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class AgentNotFoundError(AgentWorkspaceError):
    def __init__(self, agent_id: str):
        super().__init__(
            f"Agent '{agent_id}' does not exist.",
            code="AGENT_NOT_FOUND",
            details={"agent_id": agent_id},
        )


class RAGArtifactNotFoundError(AgentWorkspaceError):
    def __init__(self, rag_id: str):
        super().__init__(
            f"Referenced RAG artifact '{rag_id}' does not exist in the workspace library.",
            code="RAG_ARTIFACT_NOT_FOUND",
            details={"rag_id": rag_id},
        )


class NoAttachedRAGError(AgentWorkspaceError):
    def __init__(self, agent_id: str):
        super().__init__(
            f"Agent '{agent_id}' has no attached RAG knowledge artifacts to retrieve from.",
            code="NO_ATTACHED_RAG",
            details={"agent_id": agent_id},
        )
