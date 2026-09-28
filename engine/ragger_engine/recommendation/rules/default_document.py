"""
Rule: RULE_DEFAULT_DOCUMENT
Condition: Flat prose documents, modest length, absence of complex tables or deep hierarchies.
Target: Document RAG (Baseline fallback rule)
"""

from typing import List

from .base import RecommendationRule
from ..models import RagArchitectureId, RuleEvaluationResult
from ragger_engine.analyzer.models import FileAnalysisProfile, WorkspaceKnowledgeProfile


class RuleDefaultDocument(RecommendationRule):
    @property
    def rule_id(self) -> str:
        return "RULE_DEFAULT_DOCUMENT"

    @property
    def priority(self) -> int:
        return 10

    @property
    def base_confidence(self) -> float:
        return 0.60

    def evaluate(
        self,
        workspace_profile: WorkspaceKnowledgeProfile,
        file_profiles: List[FileAnalysisProfile],
    ) -> RuleEvaluationResult:
        signals: List[str] = [
            "Standard prose documents and narrative content observed",
            "Uniform document structure without deep heading hierarchies or major tabular splits",
        ]

        return RuleEvaluationResult(
            rule_id=self.rule_id,
            matched=True,
            confidence_score=self.base_confidence,
            detected_signals=signals,
            target_architecture=RagArchitectureId.DOCUMENT_RAG,
        )
