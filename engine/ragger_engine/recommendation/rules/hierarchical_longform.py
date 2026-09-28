"""
Rule: RULE_HIERARCHICAL_LONGFORM
Condition: Dominant modality is hierarchical document with heading depth >= 2.
Target: Hierarchical Knowledge RAG

Note: Strictly uses authoritative Phase 3 structural facts. Does not use unmeasured word_count.
"""

from typing import List

from .base import RecommendationRule
from ..models import RagArchitectureId, RuleEvaluationResult
from ragger_engine.analyzer.models import ContentModality, FileAnalysisProfile, WorkspaceKnowledgeProfile


class RuleHierarchicalLongform(RecommendationRule):
    @property
    def rule_id(self) -> str:
        return "RULE_HIERARCHICAL_LONGFORM"

    @property
    def priority(self) -> int:
        return 80

    @property
    def base_confidence(self) -> float:
        return 0.80

    def evaluate(
        self,
        workspace_profile: WorkspaceKnowledgeProfile,
        file_profiles: List[FileAnalysisProfile],
    ) -> RuleEvaluationResult:
        is_hierarchical_dominant = (
            workspace_profile.dominant_modality == ContentModality.HIERARCHICAL_DOCUMENT.value
            or workspace_profile.modality_distribution.get(ContentModality.HIERARCHICAL_DOCUMENT.value, 0.0) >= 0.50
        )
        max_depth = max([fp.structural_facts.heading_depth for fp in file_profiles], default=0)
        deep_heading_sources = [
            fp for fp in file_profiles
            if fp.structural_facts.heading_depth >= 2
        ]

        has_deep_headings = (max_depth >= 2) or (len(deep_heading_sources) > 0)
        matched = is_hierarchical_dominant and has_deep_headings

        signals: List[str] = []
        if matched:
            hier_pct = workspace_profile.modality_distribution.get(
                ContentModality.HIERARCHICAL_DOCUMENT.value, 0.0
            ) * 100
            signals.append(
                f"Hierarchical documents represent {hier_pct:.1f}% of workspace sources"
            )
            signals.append(
                f"Nested section structure detected with maximum heading depth of {max_depth}"
            )
            if deep_heading_sources:
                signals.append(
                    f"{len(deep_heading_sources)} sources contain multi-level heading hierarchies"
                )

        return RuleEvaluationResult(
            rule_id=self.rule_id,
            matched=matched,
            confidence_score=self.base_confidence if matched else 0.0,
            detected_signals=signals,
            target_architecture=RagArchitectureId.KNOWLEDGE_RAG,
        )
