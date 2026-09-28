"""
Canonical domain exceptions for Phase 6 RAG Retrieval Subsystem.
Provides structured error codes and messages for API and IPC boundary handling.
"""

from typing import Any, Dict, Optional


class RetrievalEngineError(Exception):
    """Base exception for all retrieval engine operations."""

    def __init__(self, message: str, code: str = "RETRIEVAL_ERROR", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class NoActiveBuildError(RetrievalEngineError):
    """Raised when no active build pointer or manifest exists in the workspace."""

    def __init__(self, message: str = "No active build manifest found for this workspace.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="NO_ACTIVE_BUILD", details=details)


class BuildIncompleteError(RetrievalEngineError):
    """Raised when the active build manifest status is not 'completed'."""

    def __init__(self, status: str, details: Optional[Dict[str, Any]] = None):
        msg = f"Active build cannot be retrieved because status is '{status}', expected 'completed'."
        det = details or {}
        det["status"] = status
        super().__init__(msg, code="BUILD_INCOMPLETE", details=det)


class ManifestCorruptedError(RetrievalEngineError):
    """Raised when the active build manifest fails independent canonical SHA-256 validation."""

    def __init__(self, stored_hash: str, computed_hash: str, details: Optional[Dict[str, Any]] = None):
        msg = (
            f"Active build manifest hash verification failed. "
            f"Stored: '{stored_hash}', Computed: '{computed_hash}'."
        )
        det = details or {}
        det["stored_hash"] = stored_hash
        det["computed_hash"] = computed_hash
        super().__init__(msg, code="MANIFEST_CORRUPTED", details=det)


class ArchitectureNotRetrievableError(RetrievalEngineError):
    """Raised when the active build architecture is not supported for retrieval (e.g. Graph RAG)."""

    def __init__(self, architecture: str, message: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        msg = message or f"Architecture '{architecture}' is not retrievable in this version."
        det = details or {}
        det["architecture"] = architecture
        super().__init__(msg, code="ARCHITECTURE_NOT_RETRIEVABLE", details=det)


class InvalidFilterError(RetrievalEngineError):
    """Raised when query filters violate schema constraints."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="INVALID_FILTER", details=details)


class InvalidTopKError(RetrievalEngineError):
    """Raised when top_k exceeds maximum permissible boundaries."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="INVALID_TOP_K", details=details)


class QueryEmbeddingError(RetrievalEngineError):
    """Raised when generating query embeddings fails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="QUERY_EMBEDDING_FAILED", details=details)


class BuildUnavailableError(RetrievalEngineError):
    """Raised when a specific resolved build cannot be located or loaded into the retrieval runtime."""

    def __init__(self, build_id: str, message: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        msg = message or f"Build '{build_id}' is unavailable, missing, or corrupted."
        det = details or {}
        det["build_id"] = build_id
        super().__init__(msg, code="BUILD_UNAVAILABLE", details=det)

