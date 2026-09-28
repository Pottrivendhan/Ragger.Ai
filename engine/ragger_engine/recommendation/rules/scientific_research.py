"""
Rule: RULE_SCIENTIFIC_RESEARCH
Condition: Modality classified as scientific_research or research domain >= 50%.
Target: Research-Oriented RAG
"""

from typing import List

from .base import RecommendationRule
from ..models import RagArchitectureId, RuleEvaluationResult
from ragger_engine.analyzer.models import ContentModality, FileAnalysisProfile, SemanticDensity, WorkspaceKnowledgeProfile


class RuleScientificResearch(RecommendationRule):
    @property
    def rule_id(self) -> str:
        return "RULE_SCIENTIFIC_RESEARCH"

    @property
    def priority(self) -> int:
        return 85

    @property
    def base_confidence(self) -> float:
        return 0.85

    def evaluate(
        self,
        workspace_profile: WorkspaceKnowledgeProfile,
        file_profiles: List[FileAnalysisProfile],
    ) -> RuleEvaluationResult:
        sci_modality = ContentModality.SCIENTIFIC_RESEARCH.value
        sci_ratio = workspace_profile.modality_distribution.get(sci_modality, 0.0)
        is_research_domain = workspace_profile.overall_domain == "research"
        has_dense_research = any(
            (
                fp.semantic_observations.primary_modality == ContentModality.SCIENTIFIC_RESEARCH
                or (
                    fp.semantic_observations.detected_domain == "research"
                    and fp.semantic_observations.semantic_density == SemanticDensity.HIGH
                )
            )
            for fp in file_profiles
        )

        matched = (
            workspace_profile.dominant_modality == sci_modality
            or sci_ratio >= 0.50
            or is_research_domain
            or has_dense_research
        )

        signals: List[str] = []
        if matched:
            signals.append(
                f"Scientific or academic research content identified ({sci_ratio * 100:.1f}% of sources)"
            )
            signals.append(
                "High semantic density and specialized domain terminology observed"
            )

        return RuleEvaluationResult(
            rule_id=self.rule_id,
            matched=matched,
            confidence_score=self.base_confidence if matched else 0.0,
            detected_signals=signals,
            target_architecture=RagArchitectureId.RESEARCH_RAG,
        )
