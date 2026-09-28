"""
Phase 8 Automated Quality Evaluation & Benchmarking Subsystem for Ragger.ai.
"""

from .config_manager import get_evaluation_config, save_evaluation_config
from .dataset_generator import generate_evaluation_probes
from .exceptions import (
    ArchitectureNotEvaluableError,
    EvaluationAlreadyRunningError,
    EvaluationBuildChangedError,
    EvaluationCancelledError,
    EvaluationError,
    EvaluationNotFoundError,
    InvalidEvaluationParameterError,
    ModelNotAvailableError,
    NoActiveBuildError,
)
from .metrics import (
    aggregate_deterministic_metrics,
    aggregate_judge_metrics,
    calculate_rag_quality_score,
)
from .models import (
    BuildSnapshot,
    DeterministicMetrics,
    EvaluationConfig,
    EvaluationReport,
    EvaluationRunProgress,
    EvaluationRunRequest,
    EvaluationState,
    JudgeEvaluatedMetrics,
    ProbeEvaluationResult,
    ProbeQueryItem,
    ProbeType,
    VersionEvaluationComparisonResult,
    VersionEvaluationMetricDelta,
)
from .service import EvaluationService
from .snapshot import (
    capture_build_snapshot,
    capture_build_snapshot_for_build,
    verify_build_integrity,
)

__all__ = [
    "ArchitectureNotEvaluableError",
    "BuildSnapshot",
    "DeterministicMetrics",
    "EvaluationAlreadyRunningError",
    "EvaluationBuildChangedError",
    "EvaluationCancelledError",
    "EvaluationConfig",
    "EvaluationError",
    "EvaluationNotFoundError",
    "EvaluationReport",
    "EvaluationRunProgress",
    "EvaluationRunRequest",
    "EvaluationService",
    "EvaluationState",
    "InvalidEvaluationParameterError",
    "JudgeEvaluatedMetrics",
    "ModelNotAvailableError",
    "NoActiveBuildError",
    "ProbeEvaluationResult",
    "ProbeQueryItem",
    "ProbeType",
    "VersionEvaluationComparisonResult",
    "VersionEvaluationMetricDelta",
    "aggregate_deterministic_metrics",
    "aggregate_judge_metrics",
    "calculate_rag_quality_score",
    "capture_build_snapshot",
    "capture_build_snapshot_for_build",
    "generate_evaluation_probes",
    "get_evaluation_config",
    "save_evaluation_config",
    "verify_build_integrity",
]
