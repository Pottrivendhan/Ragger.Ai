/**
 * Phase 3 Analysis domain types for React Frontend.
 *
 * CRITICAL ARCHITECTURAL RULE:
 * Strictly observational types. Zero recommendation fields.
 */

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
