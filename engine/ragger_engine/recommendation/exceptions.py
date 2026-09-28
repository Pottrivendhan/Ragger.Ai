"""
Strongly typed exceptions for Phase 4 Recommendation Engine.
"""

from typing import Optional


class RecommendationError(Exception):
    """Base exception for all recommendation errors."""
    pass


class NoRecommendationAvailableError(RecommendationError):
    """Raised when no workspace profile or sources exist to evaluate."""
    pass


class InvalidConfigurationError(RecommendationError):
    """Raised when customized chunking, embedding, vector DB, or retrieval configuration is invalid."""
    pass


class ArchitectureCompatibilityError(RecommendationError):
    """Raised when chosen chunking or retrieval strategy is incompatible with target architecture."""
    pass


class ImmutableConfigMutationError(RecommendationError):
    """Raised when an attempt is made to mutate an existing frozen configuration without a revision."""
    pass


class BuildNotApprovedError(RecommendationError):
    """Raised when Phase 5 build prerequisites fail (missing, unfrozen, hash mismatch, or source drift)."""
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.details = details or {}
