"""
Domain exceptions for Phase 9 Local AI Model Manager & Hardware Adaptation Subsystem.
Strictly maps error states to HTTP status codes with structured machine-readable error details.
"""

from typing import Any, Dict, Optional


class ModelManagerError(Exception):
    """Base exception for all model manager operations."""

    def __init__(self, message: str, code: str = "MODEL_MANAGER_ERROR", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class ModelNotFoundError(ModelManagerError):
    """Raised when a requested model_key does not exist in catalog or inventory (HTTP 404)."""

    def __init__(self, model_key: str):
        super().__init__(
            message=f"Model with key '{model_key}' was not found in catalog or installed inventory.",
            code="MODEL_NOT_FOUND",
            details={"model_key": model_key},
        )


class ModelInUseError(ModelManagerError):
    """Raised when an active model in generation or evaluation configuration is targeted for deletion (HTTP 409)."""

    def __init__(self, model_key: str, referencing_configs: Dict[str, Any]):
        super().__init__(
            message=f"Model '{model_key}' is currently referenced in active workspace configurations and cannot be deleted.",
            code="MODEL_IN_USE",
            details={"model_key": model_key, "referencing_configs": referencing_configs},
        )


class DownloadAlreadyRunningError(ModelManagerError):
    """Raised when a download or pull is requested while an active download exists in that slot (HTTP 409)."""

    def __init__(self, slot: str, active_model_key: str):
        super().__init__(
            message=f"A download is already running in slot '{slot}' for model '{active_model_key}'.",
            code="DOWNLOAD_ALREADY_RUNNING",
            details={"slot": slot, "active_model_key": active_model_key},
        )


class ModelRoleMismatchError(ModelManagerError):
    """Raised when a model category is incompatible with the requested activation role (HTTP 422)."""

    def __init__(self, model_key: str, category: str, requested_role: str):
        super().__init__(
            message=f"Model '{model_key}' has category '{category}' and cannot be activated for role '{requested_role}'.",
            code="MODEL_ROLE_MISMATCH",
            details={"model_key": model_key, "category": category, "requested_role": requested_role},
        )


class InsufficientDiskSpaceError(ModelManagerError):
    """Raised during preflight when available disk space is insufficient for download (HTTP 507)."""

    def __init__(self, required_mb: int, available_mb: int, storage_dir: str):
        super().__init__(
            message=f"Insufficient disk space for download. Required: {required_mb} MB, Available: {available_mb} MB.",
            code="INSUFFICIENT_DISK_SPACE",
            details={"required_mb": required_mb, "available_mb": available_mb, "storage_dir": storage_dir},
        )


class ChecksumMismatchError(ModelManagerError):
    """Raised when downloaded artifact fails cryptographic SHA-256 integrity verification (HTTP 502)."""

    def __init__(self, model_key: str, expected_sha256: str, actual_sha256: str):
        super().__init__(
            message=f"Downloaded artifact for '{model_key}' failed SHA-256 integrity verification.",
            code="MODEL_ARTIFACT_INTEGRITY_FAILURE",
            details={
                "model_key": model_key,
                "expected_sha256": expected_sha256,
                "actual_sha256": actual_sha256,
            },
        )


class OllamaUnavailableError(ModelManagerError):
    """Raised when the local Ollama daemon is unreachable (HTTP 503)."""

    def __init__(self, host: str = "127.0.0.1:11434"):
        super().__init__(
            message=f"Local Ollama daemon is unreachable at '{host}'.",
            code="OLLAMA_UNAVAILABLE",
            details={"host": host},
        )


class CatalogConfigurationError(ModelManagerError):
    """Raised during service startup when immutable catalog definitions fail validation (Fatal)."""

    def __init__(self, reason: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=f"Catalog configuration startup validation failed: {reason}",
            code="CATALOG_CONFIGURATION_ERROR",
            details=details or {},
        )
