"""
Data models and schemas for Phase 8 Automated Quality Evaluation & Benchmarking Subsystem.
Strict validation enforced with extra='forbid' across all payload and report contracts.
"""

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class EvaluationState(str, Enum):
    """Lifecycle states for evaluation runs."""
    IDLE = "idle"
    PREFLIGHT = "preflight"
    GENERATING_DATASET = "generating_dataset"
    EVALUATING_RETRIEVAL = "evaluating_retrieval"
    EVALUATING_GENERATION = "evaluating_generation"
    AGGREGATING = "aggregating"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ProbeType(str, Enum):
    """Classification of synthetic evaluation probes."""
    IN_DOMAIN = "in_domain"
    OUT_OF_DOMAIN = "out_of_domain"


class BuildSnapshot(BaseModel):
    """Immutable snapshot of the build taken at evaluation preflight."""
    model_config = ConfigDict(extra="forbid")

    build_id: str
    manifest_id: str
    manifest_hash: str
    approved_architecture: str
    source_ids: List[str]
    source_sha256: Dict[str, str]
    chunk_count: int
    vector_count: int
    rag_id: Optional[str] = None
    version_id: Optional[str] = None
    version_tag: Optional[str] = None


class EvaluationConfig(BaseModel):
    """Application-managed configuration for evaluation runs."""
    model_config = ConfigDict(extra="forbid")

    judge_provider: str = "ollama"
    judge_model_name: str = "llama3.2:3b"
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    max_tokens: int = Field(default=1024, ge=64, le=4096)
    default_sample_size: int = Field(default=10, ge=3, le=50)
    sampling_seed: int = 42
    retrieval_top_k: int = Field(default=5, ge=1, le=20)


class EvaluationRunRequest(BaseModel):
    """Restricted client request payload to initiate an evaluation run."""
    model_config = ConfigDict(extra="forbid")

    sample_size: Optional[int] = Field(default=None, ge=3, le=50)
    sampling_seed: Optional[int] = None
    rag_id: Optional[str] = None
    version_id: Optional[str] = None


class ProbeQueryItem(BaseModel):
    """A synthesized evaluation probe query with provenance metadata."""
    model_config = ConfigDict(extra="forbid")

    probe_id: str
    probe_type: ProbeType
    query: str
    origin_chunk_id: Optional[str] = None
    origin_source_id: Optional[str] = None
    origin_source_name: Optional[str] = None
    expected_facts: Optional[str] = None
    expected_disclaimer: bool = False


class ProbeEvaluationResult(BaseModel):
    """Individual probe evaluation diagnostics and scoring."""
    model_config = ConfigDict(extra="forbid")

    probe_id: str
    probe_type: ProbeType
    query: str
    retrieved_chunk_ids: List[str]
    origin_chunk_rank: Optional[int] = None  # 1-indexed, None if not in top candidates
    hit_at_1: bool = False
    hit_at_3: bool = False
    hit_at_5: bool = False
    reciprocal_rank: float = 0.0
    retrieval_latency_ms: float = 0.0

    # Generation & Judge metrics
    generated_answer: Optional[str] = None
    disclaimer_emitted: bool = False
    correct_disclaimer: Optional[bool] = None
    total_claims: int = 0
    supported_claims: int = 0
    unsupported_claims: int = 0
    faithfulness: Optional[float] = None
    verified_citations: int = 0
    unverified_citations: int = 0
    citation_precision: Optional[float] = None
    generation_latency_ms: float = 0.0


class DeterministicMetrics(BaseModel):
    """Fully deterministic, non-LLM evaluation metrics."""
    model_config = ConfigDict(extra="forbid")

    hits_at_1: float
    hits_at_3: float
    hits_at_5: float
    mrr: float
    source_coverage: float
    citation_precision: Optional[float] = None
    retrieval_latency_p50_ms: float
    retrieval_latency_p95_ms: float


class JudgeEvaluatedMetrics(BaseModel):
    """Metrics evaluated using LLM judge claim analysis and entailment."""
    model_config = ConfigDict(extra="forbid")

    faithfulness: Optional[float] = None
    claims_total: int
    claims_supported: int
    claims_unsupported: int
    disclaimer_accuracy: float
    generation_latency_p50_ms: float
    generation_latency_p95_ms: float


class EvaluationRunProgress(BaseModel):
    """Real-time telemetry and state for active or historic evaluation runs."""
    model_config = ConfigDict(extra="forbid")

    eval_id: str
    workspace_id: str
    state: EvaluationState
    current_stage: str
    total_probes: int = 0
    processed_probes: int = 0
    percent: float = 0.0
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str
    updated_at: str


class EvaluationReport(BaseModel):
    """Authoritative, immutable evaluation report card for a build."""
    model_config = ConfigDict(extra="forbid")

    eval_id: str
    workspace_id: str
    created_at: str
    completed_at: str
    duration_ms: float
    build_snapshot: BuildSnapshot
    config: EvaluationConfig
    quality_score: float  # Composite RAG Quality Score (0.0 - 100.0)
    metric_weights_used: Dict[str, float]
    deterministic_metrics: DeterministicMetrics
    judge_evaluated_metrics: JudgeEvaluatedMetrics
    probe_results: List[ProbeEvaluationResult]
    selected_chunk_ids: List[str]
    selected_source_ids: List[str]
    rag_id: Optional[str] = None
    version_id: Optional[str] = None
    version_tag: Optional[str] = None


class VersionEvaluationMetricDelta(BaseModel):
    """Factual numeric delta between base and target metric values."""
    model_config = ConfigDict(extra="forbid")

    base_value: Optional[float]
    target_value: Optional[float]
    delta: Optional[float]


class VersionEvaluationComparisonResult(BaseModel):
    """
    Objective, factual comparison of evaluation benchmark metrics between two versions.
    Purely numeric deltas without value judgments or promotional bias.
    """
    model_config = ConfigDict(extra="forbid")

    rag_id: str
    base_eval_id: str
    target_eval_id: str
    base_version_id: Optional[str] = None
    base_version_tag: Optional[str] = None
    base_build_id: str
    target_version_id: Optional[str] = None
    target_version_tag: Optional[str] = None
    target_build_id: str

    quality_score_delta: VersionEvaluationMetricDelta
    hits_at_1_delta: VersionEvaluationMetricDelta
    hits_at_3_delta: VersionEvaluationMetricDelta
    hits_at_5_delta: VersionEvaluationMetricDelta
    mrr_delta: VersionEvaluationMetricDelta
    source_coverage_delta: VersionEvaluationMetricDelta
    citation_precision_delta: VersionEvaluationMetricDelta
    faithfulness_delta: VersionEvaluationMetricDelta
    disclaimer_accuracy_delta: VersionEvaluationMetricDelta
