"""
Rule: RULE_MIXED_MODALITY
Condition: Workspace contains document modality > 20% and tabular dataset > 20%.
Target: Hybrid Multi-Modal RAG
"""

from typing import List

from .base import RecommendationRule
from ..models import RagArchitectureId, RuleEvaluationResult
from ragger_engine.analyzer.models import ContentModality, FileAnalysisProfile, WorkspaceKnowledgeProfile


class RuleMixedModality(RecommendationRule):
    @property
    def rule_id(self) -> str:
        return "RULE_MIXED_MODALITY"

    @property
    def priority(self) -> int:
        return 95

    @property
    def base_confidence(self) -> float:
        return 0.95

    def evaluate(
        self,
        workspace_profile: WorkspaceKnowledgeProfile,
        file_profiles: List[FileAnalysisProfile],
    ) -> RuleEvaluationResult:
        dist = workspace_profile.modality_distribution
        doc_modalities = {
            ContentModality.NARRATIVE_TEXT.value,
            ContentModality.HIERARCHICAL_DOCUMENT.value,
            ContentModality.SCIENTIFIC_RESEARCH.value,
        }
        tabular_modality = ContentModality.TABULAR_DATASET.value

        doc_ratio = sum(dist.get(m, 0.0) for m in doc_modalities)
        tab_ratio = dist.get(tabular_modality, 0.0)

        # Strict > 0.20 boundary check
        matched = (doc_ratio > 0.20) and (tab_ratio > 0.20)

        signals: List[str] = []
        if matched:
            signals.append(
                f"Workspace contains mixed modalities: {doc_ratio * 100:.1f}% documents, {tab_ratio * 100:.1f}% tabular datasets"
            )
            signals.append(
                f"Unstructured prose and structured tabular records coexist across {workspace_profile.total_sources} sources"
            )
            if workspace_profile.cross_source_entity_overlap:
                overlap_sample = ", ".join(workspace_profile.cross_source_entity_overlap[:3])
                signals.append(
                    f"{len(workspace_profile.cross_source_entity_overlap)} overlapping entity concepts detected across sources ({overlap_sample})"
                )

        return RuleEvaluationResult(
            rule_id=self.rule_id,
            matched=matched,
            confidence_score=self.base_confidence if matched else 0.0,
            detected_signals=signals,
            target_architecture=RagArchitectureId.HYBRID_RAG,
        )
