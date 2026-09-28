"""
Recommendation Service.
Manages deterministic rule execution, catalog resolution, user customization,
and the immutable ApprovedBuildConfig lifecycle.
"""

import json
import os
from pathlib import Path
import threading
from typing import Dict, List, Optional, Tuple
import uuid

from .catalog import get_architecture_spec, list_architecture_specs
from .exceptions import (
    ImmutableConfigMutationError,
    NoRecommendationAvailableError,
)
from .models import (
    ApprovedBuildConfig,
    ArchitectureSpec,
    ChunkingConfig,
    ConfidenceLevel,
    EmbeddingConfig,
    RagArchitectureId,
    RecommendationResult,
    RetrievalConfig,
    RuleEvaluationResult,
    VectorDbConfig,
)
from .rules import (
    RecommendationRule,
    RuleDefaultDocument,
    RuleHierarchicalLongform,
    RuleMixedModality,
    RuleScientificResearch,
    RuleTabularDominant,
)
from .validation import (
    compute_canonical_config_hash,
    validate_approved_build_config,
    validate_architecture_compatibility,
)
from ragger_engine.core.storage import get_storage_root
from ragger_engine.analyzer.models import FileAnalysisProfile, WorkspaceKnowledgeProfile


def get_default_storage_dir() -> Path:
    return get_storage_root()


class RecommendationService:
    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or get_default_storage_dir()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.recommendation_path = self.storage_dir / "recommendation_result.json"
        self.approved_config_path = self.storage_dir / "approved_build_config.json"
        self._lock = threading.RLock()

        # Register deterministic rules
        self.rules: List[RecommendationRule] = [
            RuleMixedModality(),
            RuleTabularDominant(),
            RuleScientificResearch(),
            RuleHierarchicalLongform(),
            RuleDefaultDocument(),
        ]
        self._priority_map: Dict[str, int] = {r.rule_id: r.priority for r in self.rules}

        self._latest_recommendation: Optional[RecommendationResult] = None
        self._approved_config: Optional[ApprovedBuildConfig] = None

        self._load_persisted_state()

    def _load_persisted_state(self) -> None:
        """Loads latest recommendation and approved config from disk if available."""
        with self._lock:
            if self.recommendation_path.exists():
                try:
                    with open(self.recommendation_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self._latest_recommendation = RecommendationResult.model_validate(data)
                except Exception:
                    self._latest_recommendation = None

            if self.approved_config_path.exists():
                try:
                    with open(self.approved_config_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self._approved_config = ApprovedBuildConfig.model_validate(data)
                except Exception:
                    self._approved_config = None

    def evaluate(
        self,
        workspace_profile: WorkspaceKnowledgeProfile,
        file_profiles: List[FileAnalysisProfile],
    ) -> RecommendationResult:
        """
        Deterministically evaluates workspace knowledge profile and constituent file profiles.
        Zero LLM calls, zero network requests.
        """
        if workspace_profile.total_sources == 0:
            raise NoRecommendationAvailableError("Cannot evaluate recommendation for an empty workspace.")

        with self._lock:
            evaluated_rules: List[RuleEvaluationResult] = []
            for rule in self.rules:
                res = rule.evaluate(workspace_profile, file_profiles)
                evaluated_rules.append(res)

            # Filter matched rules
            matched = [r for r in evaluated_rules if r.matched]
            if not matched:
                # Fallback to default document rule if somehow none matched
                fallback_rule = RuleDefaultDocument()
                matched = [fallback_rule.evaluate(workspace_profile, file_profiles)]

            # Sort matched rules by (confidence_score, priority) descending
            matched.sort(
                key=lambda r: (r.confidence_score, self._priority_map.get(r.rule_id, 0)),
                reverse=True,
            )

            winning_rule = matched[0]
            winning_spec = get_architecture_spec(winning_rule.target_architecture)

            # Deterministic resolution of alternatives:
            # 1. Other matched rules in rank order
            # 2. Winning architecture's registered alternative_options
            # 3. Graph RAG (advanced alternative option)
            alt_order: List[RagArchitectureId] = []
            for m in matched[1:]:
                if m.target_architecture != winning_rule.target_architecture and m.target_architecture not in alt_order:
                    alt_order.append(m.target_architecture)

            for opt in winning_spec.alternative_options:
                if opt != winning_rule.target_architecture and opt not in alt_order:
                    alt_order.append(opt)

            # Include Graph RAG at the end if not already present
            if RagArchitectureId.GRAPH_RAG not in alt_order and winning_rule.target_architecture != RagArchitectureId.GRAPH_RAG:
                alt_order.append(RagArchitectureId.GRAPH_RAG)

            alternative_specs = [get_architecture_spec(a) for a in alt_order]

            # Determine confidence level
            score = winning_rule.confidence_score
            if score >= 0.85:
                level = ConfidenceLevel.HIGH
            elif score >= 0.70:
                level = ConfidenceLevel.MEDIUM
            else:
                level = ConfidenceLevel.LOW

            result = RecommendationResult(
                recommendation_id=f"rec_{uuid.uuid4().hex[:12]}",
                recommended_architecture=winning_rule.target_architecture,
                architecture_spec=winning_spec,
                confidence_score=score,
                confidence_level=level,
                matched_rule_id=winning_rule.rule_id,
                detected_signals=winning_rule.detected_signals,
                alternative_architectures=alternative_specs,
                evaluated_rules=evaluated_rules,
            )

            # Persist to disk atomically
            temp_path = self.recommendation_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(result.model_dump(mode="json"), f, indent=2)
            temp_path.replace(self.recommendation_path)

            self._latest_recommendation = result
            return result

    def get_current_recommendation(self) -> Optional[RecommendationResult]:
        """Returns latest recommendation result."""
        with self._lock:
            return self._latest_recommendation

    def get_all_architectures(self) -> List[ArchitectureSpec]:
        """Returns catalog of all supported architectures."""
        return list_architecture_specs()

    def approve_configuration(
        self,
        workspace_id: str,
        approved_architecture_id: RagArchitectureId,
        source_ids: List[str],
        custom_chunking: Optional[ChunkingConfig] = None,
        custom_embedding: Optional[EmbeddingConfig] = None,
        custom_vector_db: Optional[VectorDbConfig] = None,
        custom_retrieval: Optional[RetrievalConfig] = None,
        is_revision: bool = False,
    ) -> ApprovedBuildConfig:
        """
        Approves and freezes an ApprovedBuildConfig snapshot.
        Enforces immutability: existing frozen configuration cannot be silently overwritten without is_revision=True.
        """
        with self._lock:
            existing = self.get_approved_config()
            config_version = 1

            if existing is not None:
                if existing.is_frozen and not is_revision:
                    raise ImmutableConfigMutationError(
                        f"Configuration '{existing.config_id}' (v{existing.config_version}) is already frozen. "
                        "To update approved configuration, request a new revision (is_revision=True)."
                    )
                if is_revision:
                    config_version = existing.config_version + 1

            spec = get_architecture_spec(approved_architecture_id)

            chunking = custom_chunking or spec.default_chunking
            embedding = custom_embedding or spec.default_embedding
            vector_db = custom_vector_db or spec.default_vector_db
            retrieval = custom_retrieval or spec.default_retrieval

            # Validate architecture compatibility
            validate_architecture_compatibility(approved_architecture_id, chunking, retrieval)

            # Determine recommended architecture
            rec = self.get_current_recommendation()
            recommended_arch = rec.recommended_architecture if rec else approved_architecture_id
            rec_id = rec.recommendation_id if rec else None

            # Detect if user customized settings or selected an alternative
            user_customized = (
                approved_architecture_id != recommended_arch
                or custom_chunking is not None
                or custom_embedding is not None
                or custom_vector_db is not None
                or custom_retrieval is not None
            )

            # Compute cryptographic hash
            config_hash = compute_canonical_config_hash(
                architecture_id=approved_architecture_id,
                chunking_config=chunking,
                embedding_config=embedding,
                vector_db_config=vector_db,
                retrieval_config=retrieval,
                source_ids=source_ids,
            )

            approved_config = ApprovedBuildConfig(
                config_id=f"cfg_{uuid.uuid4().hex[:12]}",
                config_version=config_version,
                config_hash=config_hash,
                created_from_recommendation_id=rec_id,
                workspace_id=workspace_id,
                recommended_architecture=recommended_arch,
                approved_architecture=approved_architecture_id,
                user_customized=user_customized,
                source_ids=sorted(list(set(source_ids))),
                chunking_config=chunking,
                embedding_config=embedding,
                vector_db_config=vector_db,
                retrieval_config=retrieval,
                is_frozen=True,
            )

            # Persist snapshot atomically
            temp_path = self.approved_config_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(approved_config.model_dump(mode="json"), f, indent=2)
            temp_path.replace(self.approved_config_path)

            self._approved_config = approved_config
            return approved_config

    def get_approved_config(self) -> Optional[ApprovedBuildConfig]:
        """Returns the current frozen ApprovedBuildConfig snapshot."""
        with self._lock:
            return self._approved_config

    def validate_build_prerequisites(
        self,
        current_source_ids: Optional[List[str]] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validates the Phase 5 build prerequisites contract against the frozen snapshot on disk.
        """
        with self._lock:
            return validate_approved_build_config(self.approved_config_path, current_source_ids)
