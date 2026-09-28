"""
Canonical domain exceptions for Phase 7 Grounded Generation Subsystem.
"""

from typing import Any, Dict, Optional


class GenerationError(Exception):
    """Base exception for all generation and chat engine operations."""

    def __init__(self, message: str, code: str = "GENERATION_ERROR", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class ModelNotAvailableError(GenerationError):
    """Raised when the configured generation model is not available locally."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="MODEL_NOT_AVAILABLE", details=details)


class GenerationCancelledError(GenerationError):
    """Raised when an active generation is stopped by the user."""

    def __init__(self, message: str = "Generation was cancelled by the user.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="GENERATION_CANCELLED", details=details)


class SessionNotFoundError(GenerationError):
    """Raised when a chat session does not exist or does not belong to the current workspace."""

    def __init__(self, session_id: str, workspace_id: str, details: Optional[Dict[str, Any]] = None):
        msg = f"Chat session '{session_id}' not found in workspace '{workspace_id}'."
        det = details or {}
        det["session_id"] = session_id
        det["workspace_id"] = workspace_id
        super().__init__(msg, code="SESSION_NOT_FOUND", details=det)


class InvalidGenerationParameterError(GenerationError):
    """Raised when generation parameters violate constraints."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="INVALID_GENERATION_PARAMETER", details=details)
