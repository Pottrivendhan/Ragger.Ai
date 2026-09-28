/**
 * Shared IPC data contracts between Electron Main, Preload, and Renderer.
 */

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

export interface AuthenticatedHealthResponse {
  status: string;
  service: string;
  version: string;
  authenticated: boolean;
  process_id: number;
}

export interface RuntimeDiagnosticsResponse {
  python_version: string;
  platform: string;
  engine_version: string;
  process_id: number;
  environment: string;
  host: string;
  port: number;
}

export interface SupervisorStatus {
  is_running: boolean;
  pid: number | null;
  port: number | null;
  host: string;
  authenticated: boolean;
  error: string | null;
  last_health_check: string | null;
}

export interface IPCResult<T> {
  success: boolean;
  data?: T;
  error?: string;
}

export interface DetectedFileType {
  format: string;
  mime_type: string;
  confidence: number;
  detection_method: string;
  warnings: string[];
}

export interface SourceRecord {
  source_id: string;
  original_filename: string;
  detected_format: string;
  mime_type: string;
  file_size_bytes: number;
  sha256_checksum: string;
  created_at: string;
  status: string;
  warnings: string[];
}

export interface AnalysisSample {
  source_id: string;
  sample_type: 'document' | 'dataset';
  total_units: number;
  sampled_units: number;
  estimated_tokens: number;
  sample_text?: string;
  tabular_sample?: {
    sheets: Array<{
      sheet_name: string;
      total_rows: number;
      sampled_rows: number;
      columns: Array<{ name: string; inferred_type: string }>;
      sample_records: Array<Record<string, any>>;
    }>;
  };
  coverage_ratio: number;
  strategy: string;
  deterministic_seed: number;
}

export interface IngestionResult {
  source: SourceRecord;
  detected_type: DetectedFileType;
  model_type: 'document' | 'dataset';
  normalized_model: any;
  sample: AnalysisSample;
  parsing_duration_ms: number;
  warnings: string[];
}

export interface StructuralFacts {
  source_id: string;
  detected_format: string;
  file_size_bytes: number;
  heading_depth: number;
  table_count: number;
  tabular_ratio: number;
  page_count?: number | null;
  slide_count?: number | null;
  total_words: number;
  total_rows?: number | null;
  total_columns?: number | null;
  has_numerical_columns: boolean;
  has_hierarchical_headings: boolean;
  extraction_warnings: string[];
}

export interface SemanticObservations {
  detected_domain: string;
  primary_modality: string;
  secondary_modalities: string[];
  semantic_density: 'low' | 'medium' | 'high';
  entity_relationship_density: 'low' | 'medium' | 'high';
  key_entities: string[];
  primary_language: string;
  extraction_quality_score: number;
  observed_characteristics: string[];
  summary_description: string;
}

export interface ProviderTelemetry {
  requested_provider: string;
  actual_provider: string;
  fallback_used: boolean;
  fallback_reason?: string | null;
  model_name?: string | null;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  duration_ms: number;
}

export interface FileAnalysisProfile {
  source_id: string;
  original_filename: string;
  structural_facts: StructuralFacts;
  semantic_observations: SemanticObservations;
  telemetry: ProviderTelemetry;
  analyzed_at: string;
}

export interface WorkspaceKnowledgeProfile {
  workspace_id: string;
  total_sources: number;
  is_homogeneous: boolean;
  modality_distribution: Record<string, number>;
  dominant_modality: string;
  cross_source_entity_overlap: string[];
  overall_domain: string;
  file_profiles: Record<string, FileAnalysisProfile>;
  synthesized_at: string;
}

export interface AnalyzerProviderInfo {
  id: string;
  name: string;
  description: string;
  available: boolean;
  is_default: boolean;
}

export type RagArchitectureId =
  | 'document_rag'
  | 'knowledge_rag'
  | 'structured_data_rag'
  | 'hybrid_rag'
  | 'research_rag'
  | 'graph_rag';

export type ConfidenceLevel = 'high' | 'medium' | 'low';

export type RetrievalStrategy =
  | 'dense_vector_top_k'
  | 'parent_expansion'
  | 'dual_query_route'
  | 'hybrid_rrf'
  | 'dense_sparse_rerank'
  | 'graph_traversal';

export type ChunkingStrategyType =
  | 'boundary_paragraph'
  | 'parent_child_hierarchical'
  | 'tabular_schema_summary'
  | 'section_aware'
  | 'entity_graph';

export interface ChunkingConfig {
  strategy: ChunkingStrategyType;
  chunk_size: number;
  chunk_overlap: number;
  child_chunk_size?: number | null;
  parent_chunk_size?: number | null;
}

export interface EmbeddingConfig {
  provider: string;
  model_name: string;
  dimension: number;
}

export interface VectorDbConfig {
  provider: string;
  metric: string;
  index_type: string;
}

export interface RetrievalConfig {
  strategy: RetrievalStrategy;
  top_k: number;
  rerank_enabled: boolean;
  rrf_k?: number | null;
}

export interface ArchitectureSpec {
  architecture_id: RagArchitectureId;
  title: string;
  tagline: string;
  why_recommended: string;
  strengths: string[];
  tradeoffs: string[];
  alternative_options: RagArchitectureId[];
  default_chunking: ChunkingConfig;
  default_embedding: EmbeddingConfig;
  default_vector_db: VectorDbConfig;
  default_retrieval: RetrievalConfig;
}

export interface RuleEvaluationResult {
  rule_id: string;
  matched: boolean;
  confidence_score: number;
  detected_signals: string[];
  target_architecture: RagArchitectureId;
}

export interface RecommendationResult {
  recommendation_id: string;
  recommended_architecture: RagArchitectureId;
  architecture_spec: ArchitectureSpec;
  confidence_score: number;
  confidence_level: ConfidenceLevel;
  matched_rule_id: string;
  detected_signals: string[];
  alternative_architectures: ArchitectureSpec[];
  evaluated_rules: RuleEvaluationResult[];
  evaluated_at: string;
}

export interface ApprovedBuildConfig {
  config_id: string;
  config_version: number;
  config_hash: string;
  created_from_recommendation_id?: string | null;
  workspace_id: string;
  recommended_architecture: RagArchitectureId;
  approved_architecture: RagArchitectureId;
  user_customized: boolean;
  source_ids: string[];
  chunking_config: ChunkingConfig;
  embedding_config: EmbeddingConfig;
  vector_db_config: VectorDbConfig;
  retrieval_config: RetrievalConfig;
  approved_at: string;
  is_frozen: boolean;
}

export interface BuildPrerequisiteValidationResult {
  valid: boolean;
  config_id?: string | null;
  config_version?: number | null;
  config_hash?: string | null;
  approved_architecture?: string | null;
}

export type BuildStage =
  | 'idle'
  | 'preflight'
  | 'chunking'
  | 'embedding'
  | 'indexing'
  | 'verifying'
  | 'completed'
  | 'failed'
  | 'cancel_requested'
  | 'cancelled';

export interface BuildProgress {
  build_id: string | null;
  status: string;
  current_stage: BuildStage;
  chunks_total: number;
  chunks_processed: number;
  vectors_total: number;
  vectors_processed: number;
  embedding_dimension: number;
  elapsed_seconds: number;
  error_code: string | null;
  message: string | null;
  log_messages: string[];
}

export interface BuildManifest {
  manifest_id: string;
  workspace_id: string;
  build_id: string;
  config_id: string;
  config_version: number;
  config_hash: string;
  source_ids: string[];
  source_hashes: Record<string, string>;
  approved_architecture: string;
  chunking_config: Record<string, any>;
  embedding_config: Record<string, any>;
  vector_db_config: Record<string, any>;
  retrieval_config: Record<string, any>;
  chunk_count: number;
  vector_count: number;
  embedding_dimension: number;
  embedding_model: string;
  vector_store: string;
  started_at: string;
  completed_at: string;
  build_duration_ms: number;
  manifest_hash: string;
  status: string;
}

export type ScoreType = 'cosine_similarity' | 'rrf' | 'lexical_dense' | 'structured_match';

export interface RetrievalFilter {
  source_ids?: string[];
  source_name?: string;
  page_numbers?: number[];
  chunk_types?: string[];
  heading_contains?: string;
}

export interface RetrievalQuery {
  query: string;
  top_k?: number;
  filters?: RetrievalFilter;
}

export interface CitationProvenance {
  source_id: string;
  source_name: string;
  source_sha256: string;
  chunk_id: string;
  chunk_type: string;
  page_number?: number | null;
  paragraph_index?: number | null;
  heading_path: string[];
  token_count: number;
}

export interface RetrievedChunk {
  chunk_id: string;
  text: string;
  score: number;
  score_type: ScoreType;
  provenance: CitationProvenance;
  parent_chunk_id?: string | null;
  parent_text?: string | null;
  matched_child_snippets: string[];
  citation: string;
}

export interface RetrievalResponse {
  query: string;
  architecture: string;
  strategy: string;
  results: RetrievedChunk[];
  total_candidates: number;
  latency_ms: number;
  manifest_id: string;
  manifest_hash: string;
  grounded_context_prompt: string;
}

export interface RetrievalStatus {
  has_active_build: boolean;
  active_build_id?: string | null;
  manifest_id?: string | null;
  manifest_hash?: string | null;
  approved_architecture?: string | null;
  chunk_count: number;
  vector_count: number;
  embedding_model?: string | null;
  vector_store?: string | null;
  retrieval_strategy?: string | null;
}

// ---------------------------------------------------------------------------
// Phase 7 Grounded Generation & Interactive RAG Chat Types
// ---------------------------------------------------------------------------

export type GenerationState = "idle" | "retrieving" | "generating" | "completed" | "cancelled" | "failed";
export type CitationValidationStatus = "verified" | "unverified_detected" | "no_citations";
export type ChatRole = "user" | "assistant";

export interface MessageCitation {
  chunk_id: string;
  source_name: string;
  page_number?: number | null;
  citation_text: string;
}

export interface ChatMessage {
  message_id: string;
  role: ChatRole;
  content: string;
  timestamp: string;
  valid_citations: MessageCitation[];
  unverified_citation_keys: string[];
  has_insufficient_evidence: boolean;
}

export interface ChatSession {
  session_id: string;
  workspace_id: string;
  title: string;
  messages: ChatMessage[];
  created_at: string;
  updated_at: string;
}

export interface GenerationConfig {
  provider: string;
  model_name: string;
  temperature: number;
  max_tokens: number;
}

export interface ChatQueryRequest {
  query: string;
  session_id?: string;
  top_k?: number;
  filters?: RetrievalFilter;
  temperature?: number;
}

export interface GenerationResponse {
  session_id: string;
  message_id: string;
  state: GenerationState;
  answer: string;
  valid_citations: MessageCitation[];
  unverified_citation_keys: string[];
  citation_validation_status: CitationValidationStatus;
  retrieved_chunk_count: number;
  has_insufficient_evidence: boolean;
  retrieval_latency_ms: number;
  generation_latency_ms: number;
}

// ---------------------------------------------------------------------------
// Phase 8 Automated Quality Evaluation & Benchmarking Types
// ---------------------------------------------------------------------------

export type EvaluationState =
  | "idle"
  | "preflight"
  | "generating_dataset"
  | "evaluating_retrieval"
  | "evaluating_generation"
  | "aggregating"
  | "verifying"
  | "completed"
  | "cancel_requested"
  | "cancelled"
  | "failed";

export type ProbeType = "in_domain" | "out_of_domain";

export interface BuildSnapshot {
  build_id: string;
  manifest_id: string;
  manifest_hash: string;
  approved_architecture: string;
  source_ids: string[];
  source_sha256: Record<string, string>;
  chunk_count: number;
  vector_count: number;
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
}

// ==========================================
// Phase 9: Local Model Manager Contracts
// ==========================================

export type ModelCategory = 'generation' | 'embedding' | 'embeddings' | 'reranking' | 'evaluation_judge' | 'analyzer' | 'judge';
export type ModelFormat = 'gguf' | 'onnx' | 'ollama';
export type InstalledStatus = 'ready' | 'downloading' | 'paused' | 'failed' | 'corrupt';
export type DownloadState = 'idle' | 'downloading' | 'paused' | 'completed' | 'failed' | 'cancelled';
export type HardwareTier = 'low' | 'mid' | 'high' | 'ultra';

export interface StorageCapabilities {
  total_mb: number;
  available_mb: number;
  models_dir: string;
}

export interface HardwareCapabilities {
  // Flat/transformed properties
  ram_total_mb?: number;
  ram_available_mb?: number;
  ram_tier?: HardwareTier;
  has_gpu?: boolean;
  gpu_name?: string | null;
  vram_total_mb?: number | null;
  gpu_tier?: HardwareTier;
  final_tier?: HardwareTier;
  cpu_threads?: number;
  supports_avx2?: boolean;
  supports_avx512?: boolean;
  recommended_max_parameter_size?: string;
  cached_at?: string;
  cache_ttl_seconds?: number;

  // Direct HardwareProfile mapping from engine
  cpu?: {
    logical_cores: number;
    physical_cores: number;
    avx2: boolean;
    avx512: boolean;
  };
  memory?: {
    total_mb: number;
    available_mb: number;
  };
  gpu?: {
    name: string;
    vendor: string;
    vram_mb: number;
    cuda_available: boolean;
    vulkan_available: boolean;
    directml_available: boolean;
  } | null;
  storage?: StorageCapabilities | null;
  hardware_tier?: HardwareTier;
  detection_method?: string;
  detection_warnings?: string[];
  probed_at?: string;
}

export interface CatalogModelSpec {
  model_id: string;
  model_key: string;
  format: ModelFormat;
  revision: string;
  category: ModelCategory;
  download_url?: string | null;
  size_bytes: number;
  sha256?: string | null;
  parameter_size: string;
  ram_required_mb: number;
  vram_recommended_mb: number;
  context_length: number;
  description: string;
  runtime_model_ref: string;
  is_compatible: boolean;
  compatibility_reason?: string | null;
  recommended: boolean;
  ollama_name?: string | null;
}

export interface CatalogResponse {
  models: CatalogModelSpec[];
  hardware_tier: HardwareTier;
  hardware_summary: string;
}

export interface DownloadProgress {
  model_key: string;
  bytes_downloaded: number;
  bytes_total: number;
  percent: number;
  speed_bytes_per_sec: number;
  state: DownloadState;
  resumable: boolean;
  error_message?: string | null;
}

export interface InstalledModelInfo {
  model_key: string;
  model_id: string;
  format: ModelFormat;
  revision: string;
  category: ModelCategory;
  file_path?: string | null;
  size_bytes: number;
  sha256_verified: boolean;
  status: InstalledStatus;
  installed_at: string;
  in_use: boolean;
  active_roles: string[];
  ollama_name?: string | null;
  ollama_digest?: string | null;
  parameter_size?: string | null;
}

export interface InstalledInventoryResponse {
  models: InstalledModelInfo[];
  total_count: number;
  total_size_bytes: number;
}

export interface OllamaDaemonStatus {
  available: boolean;
  version?: string | null;
  installed_count: number;
  message: string;
}

export interface ModelActivationRequest {
  model_key: string;
  target_role: 'generation' | 'evaluation';
}

export interface ModelActivationResponse {
  success: boolean;
  target_role: string;
  model_key: string;
  runtime_model_ref: string;
  message: string;
}


