/**
 * TypeScript types for Phase 9 Local AI Model Manager & Hardware Adaptation.
 */

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
