"""
Canonical Domain Exceptions for Phase 8 Automated Quality Evaluation & Benchmarking Subsystem.
"""

from typing import Any, Dict, Optional


class EvaluationError(Exception):
    """Base exception for all Evaluation Engine errors."""

    def __init__(self, message: str, code: str = "EVALUATION_ERROR", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class NoActiveBuildError(EvaluationError):
    """Raised when evaluation is requested but no active build exists in the workspace (HTTP 412)."""

    def __init__(self, workspace_id: str):
        super().__init__(
            f"No active build found for workspace '{workspace_id}'. A build must be created and active before evaluation.",
            code="NO_ACTIVE_BUILD",
            details={"workspace_id": workspace_id},
        )


class ArchitectureNotEvaluableError(EvaluationError):
    """Raised when attempting evaluation on an architecture not supported for evaluation (e.g. Graph RAG) (HTTP 422)."""

    def __init__(self, architecture: str):
        super().__init__(
            f"Architecture '{architecture}' is deferred and cannot be evaluated in Phase 8.",
            code="ARCHITECTURE_NOT_EVALUATABLE",
            details={"architecture": architecture},
        )


class EvaluationAlreadyRunningError(EvaluationError):
    """Raised when an evaluation run is already active in the workspace (HTTP 409)."""

    def __init__(self, workspace_id: str, active_eval_id: str):
        super().__init__(
            f"An evaluation job ('{active_eval_id}') is already running for workspace '{workspace_id}'. "
            "Only one active evaluation job per workspace is permitted.",
            code="EVALUATION_ALREADY_RUNNING",
            details={"workspace_id": workspace_id, "active_eval_id": active_eval_id},
        )


class EvaluationBuildChangedError(EvaluationError):
    """Raised when the active build changes underneath an ongoing evaluation run (HTTP 409)."""

    def __init__(self, original_build_id: str, current_build_id: str):
        super().__init__(
            f"Active build changed during evaluation from '{original_build_id}' to '{current_build_id}'. "
            "Evaluation report discarded to preserve build integrity.",
            code="EVALUATION_BUILD_CHANGED",
            details={"original_build_id": original_build_id, "current_build_id": current_build_id},
        )


class EvaluationNotFoundError(EvaluationError):
    """Raised when the requested evaluation ID or report is not found or belongs to another workspace (HTTP 404)."""

    def __init__(self, eval_id: str, workspace_id: str):
        super().__init__(
            f"Evaluation report or job '{eval_id}' was not found in workspace '{workspace_id}'.",
            code="EVALUATION_NOT_FOUND",
            details={"eval_id": eval_id, "workspace_id": workspace_id},
        )


class ModelNotAvailableError(EvaluationError):
    """Raised when the requested evaluation judge model is not locally available in Ollama (HTTP 424)."""

    def __init__(self, model_name: str, reason: Optional[str] = None):
        msg = f"Evaluation judge model '{model_name}' is not available."
        if reason:
            msg += f" Reason: {reason}"
        super().__init__(
            msg,
            code="MODEL_NOT_AVAILABLE",
            details={"model_name": model_name, "reason": reason},
        )


class EvaluationCancelledError(EvaluationError):
    """Raised when an active evaluation run is terminated by user cancellation (HTTP 499)."""

    def __init__(self, eval_id: str):
        super().__init__(
            f"Evaluation job '{eval_id}' was cancelled by user.",
            code="EVALUATION_CANCELLED",
            details={"eval_id": eval_id},
        )


class InvalidEvaluationParameterError(EvaluationError):
    """Raised when invalid parameters are supplied to evaluation (HTTP 400)."""

    def __init__(self, message: str, parameter: Optional[str] = None):
        super().__init__(
            message,
            code="INVALID_EVALUATION_PARAMETER",
            details={"parameter": parameter} if parameter else {},
        )
