"""
Rule: RULE_TABULAR_DOMINANT
Condition: Tabular datasets account for >= 70% of uploaded sources.
Target: Structured Data RAG
"""

from typing import List

from .base import RecommendationRule
from ..models import RagArchitectureId, RuleEvaluationResult
from ragger_engine.analyzer.models import ContentModality, FileAnalysisProfile, WorkspaceKnowledgeProfile


class RuleTabularDominant(RecommendationRule):
    @property
    def rule_id(self) -> str:
        return "RULE_TABULAR_DOMINANT"

    @property
    def priority(self) -> int:
        return 90

    @property
    def base_confidence(self) -> float:
        return 0.90

    def evaluate(
        self,
        workspace_profile: WorkspaceKnowledgeProfile,
        file_profiles: List[FileAnalysisProfile],
    ) -> RuleEvaluationResult:
        dist = workspace_profile.modality_distribution
        tab_ratio = dist.get(ContentModality.TABULAR_DATASET.value, 0.0)

        matched = tab_ratio >= 0.70

        signals: List[str] = []
        if matched:
            signals.append(
                f"Tabular datasets represent {tab_ratio * 100:.1f}% of workspace sources"
            )
            tables = sum(fp.structural_facts.table_count or 0 for fp in file_profiles)
            signals.append(
                f"Structured schemas detected with {tables} tables and typed column definitions"
            )
            num_sources = sum(1 for fp in file_profiles if fp.structural_facts.has_numerical_columns)
            if num_sources > 0:
                signals.append(
                    f"Quantitative numerical data present across {num_sources} sources"
                )

        return RuleEvaluationResult(
            rule_id=self.rule_id,
            matched=matched,
            confidence_score=self.base_confidence if matched else 0.0,
            detected_signals=signals,
            target_architecture=RagArchitectureId.STRUCTURED_DATA_RAG,
        )
