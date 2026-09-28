/**
 * Ingestion and structural normalization types for the frontend.
 */

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

export interface ColumnSchema {
  name: string;
  inferred_type: string;
  null_count: number;
  total_values: number;
}

export interface SheetSample {
  sheet_name: string;
  total_rows: number;
  sampled_rows: number;
  columns: ColumnSchema[];
  sample_records: Record<string, any>[];
}

export interface AnalysisSample {
  source_id: string;
  sample_type: 'document' | 'dataset';
  total_units: number;
  sampled_units: number;
  estimated_tokens: number;
  sample_text?: string;
  tabular_sample?: {
    sheets: SheetSample[];
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
  parsing_duration_ms?: number;
  metrics?: {
    input_size_bytes: number;
    duration_ms: number;
    parser_used: string;
    blocks_extracted?: number;
    rows_extracted?: number;
  };
  warnings: string[];
}
