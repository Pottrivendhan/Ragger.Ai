/**
 * Data contracts for Phase 12 RAG Artifact Lifecycle & Storage Contract.
 */

export type RAGStatus = 'active' | 'draft' | 'archived';

export interface RAGVersionInfo {
  version_id: string;
  version_tag: string;
  build_id: string;
  created_at: string;
  chunk_count: number;
  vector_count: number;
  manifest_hash: string;
  manifest_id?: string | null;
  embedding_model?: string | null;
  vector_store?: string | null;
}

export interface RAGArtifactRecord {
  rag_id: string;
  name: string;
  description: string;
  status: RAGStatus;
  active_version_id?: string | null;
  versions: RAGVersionInfo[];
  source_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface CreateRAGRequest {
  name: string;
  description?: string;
  initial_build_id?: string;
}

export interface UpdateRAGRequest {
  name?: string;
  description?: string;
  status?: RAGStatus;
  active_version_id?: string;
}

export interface RegisterVersionRequest {
  build_id: string;
  version_tag: string;
  set_active?: boolean;
}

export interface ExportRAGResponse {
  status: string;
  rag_id: string;
  file_path: string;
  file_name: string;
  size_bytes: number;
}

export interface VersionComparisonSummary {
  chunk_count: number;
  vector_count: number;
  sources_count: number;
  manifest_hash: string;
  embedding_model?: string | null;
  vector_store?: string | null;
  architecture?: string | null;
}

export interface VersionComparisonResult {
  rag_id: string;
  base_version_id: string;
  base_version_tag: string;
  target_version_id: string;
  target_version_tag: string;
  base: VersionComparisonSummary;
  target: VersionComparisonSummary;
  chunk_count_delta: number;
  vector_count_delta: number;
  sources_count_delta: number;
  manifest_hash_changed: boolean;
  embedding_model_changed: boolean;
  sources_added: string[];
  sources_removed: string[];
  sources_retained: string[];
}

export interface RAGSuggestionsResponse {
  rag_id: string;
  suggestions: string[];
}

