"""
Pydantic data models for Phase 9 Local AI Model Manager & Hardware Adaptation Subsystem.
Strictly enforces extra="forbid" across all configuration, telemetry, catalog, and inventory schemas.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ModelCategory(str, Enum):
    """Functional role of the model within the Ragger.ai pipeline."""
    ANALYZER = "analyzer"
    EMBEDDING = "embeddings"
    GENERATION = "generation"
    JUDGE = "judge"


class ModelFormat(str, Enum):
    """Underlying distribution and execution format of the model."""
    OLLAMA = "ollama"
    GGUF = "gguf"
    ONNX = "onnx"


class HardwareTier(str, Enum):
    """Host machine capability classification based on RAM and VRAM."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    ENTHUSIAST = "enthusiast"


class DownloadState(str, Enum):
    """State machine states for model download and pull operations."""
    IDLE = "idle"
    PREFLIGHT = "preflight"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    RESUMING = "resuming"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    FAILED = "failed"


class InstalledStatus(str, Enum):
    """Operational readiness status of an installed model."""
    READY = "ready"
    MISSING = "missing"
    CORRUPTED = "corrupted"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    VERIFYING = "verifying"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


# ---------------------------------------------------------------------------
# Hardware Inspection Schemas
# ---------------------------------------------------------------------------

class CPUCapabilities(BaseModel):
    """Observable CPU processor characteristics."""
    model_config = ConfigDict(extra="forbid")

    logical_cores: int = Field(ge=1)
    physical_cores: int = Field(ge=1)
    avx2: bool
    avx512: bool


class MemoryCapabilities(BaseModel):
    """Host physical and available system memory."""
    model_config = ConfigDict(extra="forbid")

    total_mb: int = Field(ge=1)
    available_mb: int = Field(ge=0)


class GPUCapabilities(BaseModel):
    """Graphics processing and video memory capabilities."""
    model_config = ConfigDict(extra="forbid")

    name: str
    vendor: str  # "nvidia", "amd", "intel", "unknown"
    vram_mb: int = Field(ge=0)
    cuda_available: bool
    vulkan_available: bool
    directml_available: bool


class StorageCapabilities(BaseModel):
    """Host disk storage metrics for model repository volume."""
    model_config = ConfigDict(extra="forbid")

    total_mb: int = Field(ge=1)
    available_mb: int = Field(ge=0)
    models_dir: str


class HardwareProfile(BaseModel):
    """Aggregated hardware inspection profile with deterministic tier classification."""
    model_config = ConfigDict(extra="forbid")

    cpu: CPUCapabilities
    memory: MemoryCapabilities
    gpu: Optional[GPUCapabilities] = None
    storage: Optional[StorageCapabilities] = None
    detection_method: str  # "psutil+nvml", "psutil+wmi", "psutil_fallback"
    detection_warnings: List[str] = Field(default_factory=list)
    hardware_tier: HardwareTier
    probed_at: str


# ---------------------------------------------------------------------------
# Catalog and Inventory Schemas
# ---------------------------------------------------------------------------

class CatalogModelSpec(BaseModel):
    """
    Immutable catalog specification entry for a curated, verified model.
    Direct models contain exact cryptographic SHA-256 and size invariants.
    """
    model_config = ConfigDict(extra="forbid")

    model_id: str
    model_key: str
    format: ModelFormat
    revision: str
    category: ModelCategory
    download_url: Optional[str] = None
    size_bytes: int = Field(ge=0)
    sha256: Optional[str] = None
    parameter_size: str
    quantization: Optional[str] = None
    ram_required_mb: int = Field(ge=0)
    vram_recommended_mb: int = Field(ge=0)
    context_length: int = Field(ge=512)
    description: str
    ollama_name: Optional[str] = None
    is_compatible: bool = True
    compatibility_reason: Optional[str] = None
    recommended: bool = False
    runtime_model_ref: str


class InstalledModelInfo(BaseModel):
    """Operational record of a model currently present on disk or registered in Ollama."""
    model_config = ConfigDict(extra="forbid")

    model_key: str
    model_id: str
    format: ModelFormat
    revision: str
    category: ModelCategory
    size_bytes: int = Field(ge=0)
    sha256: Optional[str] = None
    ollama_name: Optional[str] = None
    ollama_digest: Optional[str] = None
    file_path: Optional[str] = None
    installed_at: str
    status: InstalledStatus
    runtime_model_ref: str
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# Download & Progress Telemetry Schemas
# ---------------------------------------------------------------------------

class DownloadProgress(BaseModel):
    """Observable telemetry emitted during model downloads and Ollama pulls."""
    model_config = ConfigDict(extra="forbid")

    model_key: str
    slot: str  # "direct" | "ollama"
    state: DownloadState
    downloaded_bytes: int = Field(ge=0)
    total_bytes: int = Field(ge=0)
    percent: float = Field(ge=0.0, le=100.0)
    speed_bytes_per_sec: float = Field(ge=0.0)
    eta_seconds: int = Field(ge=0)
    error_message: Optional[str] = None
    updated_at: str


# ---------------------------------------------------------------------------
# Activation & Management Requests
# ---------------------------------------------------------------------------

class ActivateModelRequest(BaseModel):
    """Client request to activate an installed model for an existing pipeline role."""
    model_config = ConfigDict(extra="forbid")

    role: Optional[str] = None
    target_role: Optional[str] = None
    model_key: Optional[str] = None
    workspace_id: str = "default"


class ActivateModelResponse(BaseModel):
    """Response returned upon successful runtime configuration activation."""
    model_config = ConfigDict(extra="forbid")

    model_key: str
    role: str
    workspace_id: str
    runtime_model_ref: str
    updated_config_file: str
    updated_config: Dict[str, Any]


class OllamaStatusResponse(BaseModel):
    """Connection diagnostic probe response for the local Ollama daemon."""
    model_config = ConfigDict(extra="forbid")

    available: bool
    host: str
    message: str
    installed_count: int = 0
