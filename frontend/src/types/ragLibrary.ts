export interface RAGSourceSummary {
  source_id: string;
  filename: string;
  detected_format?: string | null;
  file_size_bytes?: number | null;
  sha256_checksum?: string | null;
}

export interface RAGSampleChunk {
  chunk_id: string;
  source_name: string;
  page_number?: number | null;
  snippet: string;
}

export interface RAGArtifact {
  rag_id: string;
  build_id: string;
  manifest_id: string;
  manifest_hash: string;
  status: string;
  approved_architecture: string;
  chunk_count: number;
  vector_count: number;
  embedding_dimension: number;
  embedding_model: string;
  vector_store: string;
  started_at?: string | null;
  completed_at?: string | null;
  build_duration_ms?: number | null;
  is_active: boolean;
  sources: RAGSourceSummary[];
}

export interface RAGArtifactDetail extends RAGArtifact {
  chunking_config: Record<string, any>;
  retrieval_config: Record<string, any>;
  sample_chunks: RAGSampleChunk[];
}
