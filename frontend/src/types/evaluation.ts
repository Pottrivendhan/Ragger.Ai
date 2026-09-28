/**
 * Types for Phase 8 Quality Evaluation & Benchmarking Subsystem.
 */

export type EvaluationState =
  | 'idle'
  | 'preflight'
  | 'generating_dataset'
  | 'evaluating_retrieval'
  | 'evaluating_generation'
  | 'aggregating'
  | 'verifying'
  | 'completed'
  | 'cancel_requested'
  | 'cancelled'
  | 'failed';

export type ProbeType = 'in_domain' | 'out_of_domain';

export interface BuildSnapshot {
  build_id: string;
  manifest_id: string;
  manifest_hash: string;
  approved_architecture: string;
  source_ids: string[];
  source_sha256: Record<string, string>;
  chunk_count: number;
  vector_count: number;
  rag_id?: string | null;
  version_id?: string | null;
  version_tag?: string | null;
}

export interface EvaluationConfig {
  judge_provider: string;
  judge_model_name: string;
  temperature: number;
  max_tokens: number;
  default_sample_size: number;
  sampling_seed: number;
  retrieval_top_k: number;
}

export interface EvaluationRunRequest {
  sample_size?: number;
  sampling_seed?: number;
  rag_id?: string | null;
  version_id?: string | null;
}

export interface ProbeEvaluationResult {
  probe_id: string;
  probe_type: ProbeType;
  query: string;
  retrieved_chunk_ids: string[];
  origin_chunk_rank?: number | null;
  hit_at_1: boolean;
  hit_at_3: boolean;
  hit_at_5: boolean;
  reciprocal_rank: number;
  retrieval_latency_ms: number;
  generated_answer?: string | null;
  disclaimer_emitted: boolean;
  correct_disclaimer?: boolean | null;
  total_claims: number;
  supported_claims: number;
  unsupported_claims: number;
  faithfulness?: number | null;
  verified_citations: number;
  unverified_citations: number;
  citation_precision?: number | null;
  generation_latency_ms: number;
}

export interface DeterministicMetrics {
  hits_at_1: number;
  hits_at_3: number;
  hits_at_5: number;
  mrr: number;
  source_coverage: number;
  citation_precision?: number | null;
  retrieval_latency_p50_ms: number;
  retrieval_latency_p95_ms: number;
}

export interface JudgeEvaluatedMetrics {
  faithfulness?: number | null;
  claims_total: number;
  claims_supported: number;
  claims_unsupported: number;
  disclaimer_accuracy: number;
  generation_latency_p50_ms: number;
  generation_latency_p95_ms: number;
}

export interface EvaluationRunProgress {
  eval_id: string;
  workspace_id: string;
  state: EvaluationState;
  current_stage: string;
  total_probes: number;
  processed_probes: number;
  percent: number;
  error_code?: string | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
}

export interface EvaluationReport {
  eval_id: string;
  workspace_id: string;
  created_at: string;
  completed_at: string;
  duration_ms: number;
  build_snapshot: BuildSnapshot;
  config: EvaluationConfig;
  quality_score: number;
  metric_weights_used: Record<string, number>;
  deterministic_metrics: DeterministicMetrics;
  judge_evaluated_metrics: JudgeEvaluatedMetrics;
  probe_results: ProbeEvaluationResult[];
  selected_chunk_ids: string[];
  selected_source_ids: string[];
  rag_id?: string | null;
  version_id?: string | null;
  version_tag?: string | null;
}

export interface EvaluationReportSummary {
  eval_id: string;
  workspace_id: string;
  created_at: string;
  completed_at: string;
  duration_ms: number;
  quality_score: number;
  build_id: string;
  chunk_count: number;
  probe_count: number;
  rag_id?: string | null;
  version_id?: string | null;
  version_tag?: string | null;
}

export interface VersionEvaluationMetricDelta {
  base_value?: number | null;
  target_value?: number | null;
  delta?: number | null;
}

export interface VersionEvaluationComparisonResult {
  rag_id: string;
  base_eval_id: string;
  target_eval_id: string;
  base_version_id?: string | null;
  base_version_tag?: string | null;
  base_build_id: string;
  target_version_id?: string | null;
  target_version_tag?: string | null;
  target_build_id: string;
  quality_score_delta: VersionEvaluationMetricDelta;
  hits_at_1_delta: VersionEvaluationMetricDelta;
  hits_at_3_delta: VersionEvaluationMetricDelta;
  hits_at_5_delta: VersionEvaluationMetricDelta;
  mrr_delta: VersionEvaluationMetricDelta;
  source_coverage_delta: VersionEvaluationMetricDelta;
  citation_precision_delta: VersionEvaluationMetricDelta;
  faithfulness_delta: VersionEvaluationMetricDelta;
  disclaimer_accuracy_delta: VersionEvaluationMetricDelta;
}
