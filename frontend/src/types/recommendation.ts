/**
 * Frontend TypeScript types for Phase 4 Recommendation Engine & Approval Workflow.
 */

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
