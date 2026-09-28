/**
 * Phase 6 Retrieval Data Contracts for Frontend.
 */

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
