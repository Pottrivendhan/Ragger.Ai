"""
Exceptions for Phase 5 RAG Builder & Pipeline Execution Engine.
Granular, categorized error types with machine-readable error codes.
"""


class BuilderError(Exception):
    """Base exception for all RAG builder operations."""

    def __init__(self, message: str, code: str = "BUILDER_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class BuildGateError(BuilderError):
    """Raised when pre-flight validation of ApprovedBuildConfig or workspace prerequisites fails."""

    def __init__(self, message: str, code: str = "BUILD_GATE_FAILED"):
        super().__init__(message, code=code)


class ArchitectureNotBuildableError(BuildGateError):
    """Raised when an architecture is non-buildable in the current phase (e.g. Graph RAG)."""

    def __init__(
        self,
        message: str = "Requested architecture is not buildable in the current phase.",
        code: str = "ARCHITECTURE_NOT_BUILDABLE",
    ):
        super().__init__(message, code=code)


class ModelNotAvailableError(BuildGateError):
    """Raised when the approved embedding model is not downloaded or reachable."""

    def __init__(
        self,
        message: str = "Approved embedding model is not available locally.",
        code: str = "MODEL_NOT_AVAILABLE",
    ):
        super().__init__(message, code=code)


class VectorDbUnavailableError(BuildGateError):
    """Raised when the approved vector database provider is not available or dependencies are missing."""

    def __init__(
        self,
        message: str = "Approved vector database provider is unavailable.",
        code: str = "VECTOR_DB_UNAVAILABLE",
    ):
        super().__init__(message, code=code)


class SourceDriftError(BuildGateError):
    """Raised when source identity or content hash diverges between approval/preflight and indexing."""

    def __init__(
        self,
        message: str = "Source drift detected: workspace files changed during or since approval.",
        code: str = "SOURCE_DRIFT_DETECTED",
    ):
        super().__init__(message, code=code)


class BuildAlreadyRunningError(BuilderError):
    """Raised when an active build is already executing for the workspace (HTTP 409)."""

    def __init__(
        self,
        message: str = "A build is currently active in this workspace.",
        active_build_id: str = "",
        code: str = "BUILD_ALREADY_RUNNING",
    ):
        super().__init__(message, code=code)
        self.active_build_id = active_build_id


class ChunkingError(BuilderError):
    """Raised when document or dataset chunking encounters an unrecoverable failure."""

    def __init__(self, message: str, code: str = "CHUNKING_FAILED"):
        super().__init__(message, code=code)


class EmbeddingError(BuilderError):
    """Raised when vector embedding computation encounters an unrecoverable failure."""

    def __init__(self, message: str, code: str = "EMBEDDING_FAILED"):
        super().__init__(message, code=code)


class IndexingError(BuilderError):
    """Raised when vector database indexing or table persistence fails."""

    def __init__(self, message: str, code: str = "INDEXING_FAILED"):
        super().__init__(message, code=code)


class RetrievalSanityError(IndexingError):
    """Raised when post-indexing self-consistency retrieval check fails to retrieve known chunk."""

    def __init__(
        self,
        message: str = "Retrieval sanity check failed: persisted index could not recover known chunk.",
        code: str = "RETRIEVAL_SANITY_FAILED",
    ):
        super().__init__(message, code=code)
