"""
Ragger.ai — Phase 5 RAG Builder & Pipeline Execution Engine.
Transforms ApprovedBuildConfig snapshots into indexed vector knowledge bases.
"""

from .exceptions import (
    ArchitectureNotBuildableError,
    BuildAlreadyRunningError,
    BuilderError,
    BuildGateError,
    ChunkingError,
    EmbeddingError,
    IndexingError,
    ModelNotAvailableError,
    RetrievalSanityError,
    SourceDriftError,
    VectorDbUnavailableError,
)
from .models import (
    BuildManifest,
    BuildProgress,
    BuildStage,
    Chunk,
    ChunkMetadata,
    ChunkType,
    SourceSnapshot,
)
from .service import BuilderService

__all__ = [
    "BuilderError",
    "BuildGateError",
    "ArchitectureNotBuildableError",
    "ModelNotAvailableError",
    "VectorDbUnavailableError",
    "SourceDriftError",
    "BuildAlreadyRunningError",
    "ChunkingError",
    "EmbeddingError",
    "IndexingError",
    "RetrievalSanityError",
    "ChunkType",
    "ChunkMetadata",
    "Chunk",
    "SourceSnapshot",
    "BuildStage",
    "BuildProgress",
    "BuildManifest",
    "BuilderService",
]
