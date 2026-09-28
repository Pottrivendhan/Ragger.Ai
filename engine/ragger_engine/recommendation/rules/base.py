"""
Base class contract for Deterministic Recommendation Rules.
"""

from abc import ABC, abstractmethod
from typing import List

from ..models import RuleEvaluationResult
from ragger_engine.analyzer.models import FileAnalysisProfile, WorkspaceKnowledgeProfile


class RecommendationRule(ABC):
    @property
    @abstractmethod
    def rule_id(self) -> str:
        """Unique identifier for this deterministic rule."""
        pass

    @property
    @abstractmethod
    def priority(self) -> int:
        """Deterministic tie-breaker integer when confidence scores are equal."""
        pass

    @property
    @abstractmethod
    def base_confidence(self) -> float:
        """Fixed product confidence score defined for this rule (0.0 to 1.0)."""
        pass

    @abstractmethod
    def evaluate(
        self,
        workspace_profile: WorkspaceKnowledgeProfile,
        file_profiles: List[FileAnalysisProfile],
    ) -> RuleEvaluationResult:
        """
        Evaluate rule against workspace knowledge profile and constituent file profiles.
        Must be 100% deterministic (Zero LLM calls, zero network requests).
        """
        pass
