"""
Recommendation Package for Ragger.ai.
"""

from .catalog import get_architecture_spec, list_architecture_specs
from .exceptions import (
    ArchitectureCompatibilityError,
    BuildNotApprovedError,
    ImmutableConfigMutationError,
    InvalidConfigurationError,
    NoRecommendationAvailableError,
    RecommendationError,
)
from .models import (
    ApprovedBuildConfig,
    ArchitectureSpec,
    ChunkingConfig,
    ChunkingStrategyType,
    ConfidenceLevel,
    EmbeddingConfig,
    RagArchitectureId,
    RecommendationResult,
    RetrievalConfig,
    RetrievalStrategy,
    RuleEvaluationResult,
    VectorDbConfig,
)
from .service import RecommendationService
from .validation import (
    compute_canonical_config_hash,
    validate_approved_build_config,
    validate_architecture_compatibility,
)

__all__ = [
    "ApprovedBuildConfig",
    "ArchitectureCompatibilityError",
    "ArchitectureSpec",
    "BuildNotApprovedError",
    "ChunkingConfig",
    "ChunkingStrategyType",
    "ConfidenceLevel",
    "EmbeddingConfig",
    "ImmutableConfigMutationError",
    "InvalidConfigurationError",
    "NoRecommendationAvailableError",
    "RagArchitectureId",
    "RecommendationError",
    "RecommendationResult",
    "RecommendationService",
    "RetrievalConfig",
    "RetrievalStrategy",
    "RuleEvaluationResult",
    "VectorDbConfig",
    "compute_canonical_config_hash",
    "get_architecture_spec",
    "list_architecture_specs",
    "validate_approved_build_config",
    "validate_architecture_compatibility",
]
