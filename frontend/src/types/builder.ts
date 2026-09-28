/**
 * TypeScript Interfaces for Phase 5 RAG Builder Subsystem.
 * Mirrors canonical Pydantic schemas in ragger_engine.builder.models.
 */

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
