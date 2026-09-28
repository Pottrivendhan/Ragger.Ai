"""Exception hierarchy for Phase 3 Analyzer Agent."""

from typing import Optional


class AnalysisError(Exception):
    """Base class for all analyzer errors."""

    def __init__(self, message: str, code: str = "ANALYSIS_ERROR", details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class ProviderUnavailableError(AnalysisError):
    """Raised when an requested LLM provider (e.g. Ollama) cannot be reached."""

    def __init__(self, message: str, provider: str, details: Optional[dict] = None):
        super().__init__(message, code="PROVIDER_UNAVAILABLE", details={"provider": provider, **(details or {})})
        self.provider = provider


class SchemaValidationError(AnalysisError):
    """Raised when analyzer output fails strict Pydantic schema validation after retries."""

    def __init__(self, message: str, raw_output: str, attempts: int):
        super().__init__(message, code="SCHEMA_VALIDATION_ERROR", details={"raw_output": raw_output[:500], "attempts": attempts})
        self.raw_output = raw_output
        self.attempts = attempts


class SourceNotIngestedError(AnalysisError):
    """Raised when requesting analysis for a source_id not registered in Phase 2."""

    def __init__(self, source_id: str):
        super().__init__(f"Source ID '{source_id}' is not registered or lacks Phase 2 sample.", code="SOURCE_NOT_FOUND", details={"source_id": source_id})
        self.source_id = source_id
