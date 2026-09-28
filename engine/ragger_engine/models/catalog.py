"""
Immutable Curated Model Catalog for Phase 9 Local AI Model Manager.
Enforces fail-closed startup validation, direct artifact cryptographic invariants,
and backend-owned hardware compatibility calculations.
"""

import re
from typing import Dict, List

from .exceptions import CatalogConfigurationError
from .models import (
    CatalogModelSpec,
    HardwareProfile,
    HardwareTier,
    ModelCategory,
    ModelFormat,
)

EMPTY_FILE_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
SHA256_REGEX = re.compile(r"^[a-f0-9]{64}$")


RAW_CATALOG: List[dict] = [
    # -------------------------------------------------------------------------
    # Direct Download Models (GGUF & ONNX) - Immutable & Cryptographically Verified
    # -------------------------------------------------------------------------
    {
        "model_id": "bge-small-en-v1.5",
        "model_key": "bge-small-en-v1.5:onnx:default-v1",
        "format": ModelFormat.ONNX,
        "revision": "default-v1",
        "category": ModelCategory.EMBEDDING,
        "download_url": "https://huggingface.co/BAAI/bge-small-en-v1.5/resolve/main/onnx/model.onnx",
        "size_bytes": 133093490,
        "sha256": "828e1496d7fabb79cfa4dcd84fa38625c0d3d21da474a00f08db0f559940cf35",
        "parameter_size": "33M",
        "quantization": "FP32",
        "ram_required_mb": 512,
        "vram_recommended_mb": 0,
        "context_length": 512,
        "description": "Fast, high-accuracy embedding encoder for local dense retrieval.",
        "runtime_model_ref": "models/embeddings/bge-small-en-v1.5.onnx",
    },
    {
        "model_id": "qwen2.5-1.5b-instruct",
        "model_key": "qwen2.5-1.5b-instruct:gguf:q4_k_m-v1",
        "format": ModelFormat.GGUF,
        "revision": "q4_k_m-v1",
        "category": ModelCategory.GENERATION,
        "download_url": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "size_bytes": 1117320736,
        "sha256": "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e",
        "parameter_size": "1.5B",
        "quantization": "Q4_K_M",
        "ram_required_mb": 2048,
        "vram_recommended_mb": 2048,
        "context_length": 32768,
        "description": "Ultra-fast instruction model for low-spec systems and rapid grounded generation.",
        "runtime_model_ref": "models/generation/qwen2.5-1.5b-instruct-q4_k_m.gguf",
    },
    {
        "model_id": "llama3.2-3b-instruct",
        "model_key": "llama3.2-3b-instruct:gguf:q4_k_m-v1",
        "format": ModelFormat.GGUF,
        "revision": "q4_k_m-v1",
        "category": ModelCategory.GENERATION,
        "download_url": "https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        "size_bytes": 2019377696,
        "sha256": "6c1a2b41161032677be168d354123594c0e6e67d2b9227c84f296ad037c728ff",
        "parameter_size": "3.2B",
        "quantization": "Q4_K_M",
        "ram_required_mb": 4096,
        "vram_recommended_mb": 4096,
        "context_length": 8192,
        "description": "High-fidelity compact generation model with state-of-the-art citation compliance.",
        "runtime_model_ref": "models/generation/llama3.2-3b-instruct-q4_k_m.gguf",
    },
    {
        "model_id": "qwen2.5-1.5b-judge",
        "model_key": "qwen2.5-1.5b-judge:gguf:q4_k_m-v1",
        "format": ModelFormat.GGUF,
        "revision": "q4_k_m-v1",
        "category": ModelCategory.JUDGE,
        "download_url": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "size_bytes": 1117320736,
        "sha256": "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e",
        "parameter_size": "1.5B",
        "quantization": "Q4_K_M",
        "ram_required_mb": 2048,
        "vram_recommended_mb": 2048,
        "context_length": 32768,
        "description": "Dedicated evaluation judge for deterministic claim extraction and disclaimer scoring.",
        "runtime_model_ref": "models/judge/qwen2.5-1.5b-judge-q4_k_m.gguf",
    },

    # -------------------------------------------------------------------------
    # Ollama Daemon Models (Managed via 127.0.0.1:11434)
    # -------------------------------------------------------------------------
    {
        "model_id": "llama3.2:3b",
        "model_key": "ollama:llama3.2:3b",
        "format": ModelFormat.OLLAMA,
        "revision": "latest",
        "category": ModelCategory.GENERATION,
        "download_url": None,
        "size_bytes": 2019000000,
        "sha256": None,
        "parameter_size": "3.2B",
        "quantization": "Q4_K_M",
        "ram_required_mb": 4096,
        "vram_recommended_mb": 4096,
        "context_length": 8192,
        "description": "Official Meta Llama 3.2 3B model hosted locally via Ollama daemon.",
        "ollama_name": "llama3.2:3b",
        "runtime_model_ref": "llama3.2:3b",
    },
    {
        "model_id": "qwen2.5:1.5b",
        "model_key": "ollama:qwen2.5:1.5b",
        "format": ModelFormat.OLLAMA,
        "revision": "latest",
        "category": ModelCategory.GENERATION,
        "download_url": None,
        "size_bytes": 986000000,
        "sha256": None,
        "parameter_size": "1.5B",
        "quantization": "Q4_K_M",
        "ram_required_mb": 2048,
        "vram_recommended_mb": 2048,
        "context_length": 32768,
        "description": "Lightweight Alibaba Qwen 2.5 1.5B model hosted via Ollama daemon.",
        "ollama_name": "qwen2.5:1.5b",
        "runtime_model_ref": "qwen2.5:1.5b",
    },
    {
        "model_id": "qwen2.5:7b",
        "model_key": "ollama:qwen2.5:7b",
        "format": ModelFormat.OLLAMA,
        "revision": "latest",
        "category": ModelCategory.GENERATION,
        "download_url": None,
        "size_bytes": 4680000000,
        "sha256": None,
        "parameter_size": "7B",
        "quantization": "Q4_K_M",
        "ram_required_mb": 8192,
        "vram_recommended_mb": 8192,
        "context_length": 32768,
        "description": "High-capability Alibaba Qwen 2.5 7B model for complex reasoning and evaluation.",
        "ollama_name": "qwen2.5:7b",
        "runtime_model_ref": "qwen2.5:7b",
    },
    {
        "model_id": "mistral:7b",
        "model_key": "ollama:mistral:7b",
        "format": ModelFormat.OLLAMA,
        "revision": "latest",
        "category": ModelCategory.GENERATION,
        "download_url": None,
        "size_bytes": 4100000000,
        "sha256": None,
        "parameter_size": "7B",
        "quantization": "Q4_0",
        "ram_required_mb": 8192,
        "vram_recommended_mb": 8192,
        "context_length": 8192,
        "description": "Mistral AI 7B Instruct model hosted locally via Ollama daemon.",
        "ollama_name": "mistral:7b",
        "runtime_model_ref": "mistral:7b",
    },
    {
        "model_id": "llama3.2:3b-judge",
        "model_key": "ollama:llama3.2:3b-judge",
        "format": ModelFormat.OLLAMA,
        "revision": "latest",
        "category": ModelCategory.JUDGE,
        "download_url": None,
        "size_bytes": 2019000000,
        "sha256": None,
        "parameter_size": "3.2B",
        "quantization": "Q4_K_M",
        "ram_required_mb": 4096,
        "vram_recommended_mb": 4096,
        "context_length": 8192,
        "description": "Meta Llama 3.2 3B allocated for automated evaluation judge scoring.",
        "ollama_name": "llama3.2:3b",
        "runtime_model_ref": "llama3.2:3b",
    },
]


def validate_catalog(raw_catalog: List[dict]) -> List[CatalogModelSpec]:
    """
    Validates the catalog on service startup, failing closed if any entry
    contains invalid URLs, non-positive sizes, malformed hashes, or empty-file hashes.
    """
    validated: List[CatalogModelSpec] = []
    seen_keys: set = set()

    for item in raw_catalog:
        model_key = item.get("model_key")
        if not model_key:
            raise CatalogConfigurationError("Catalog entry missing 'model_key'", item)

        if model_key in seen_keys:
            raise CatalogConfigurationError(f"Duplicate 'model_key' detected: '{model_key}'", item)
        seen_keys.add(model_key)

        fmt = item.get("format")
        if fmt in (ModelFormat.GGUF, ModelFormat.ONNX):
            url = item.get("download_url")
            if not url or not url.startswith("https://"):
                raise CatalogConfigurationError(f"Direct model '{model_key}' must have an HTTPS download URL", item)

            size = item.get("size_bytes", 0)
            if not isinstance(size, int) or size <= 0:
                raise CatalogConfigurationError(f"Direct model '{model_key}' must have positive integer size_bytes", item)

            sha = item.get("sha256")
            if not sha or not SHA256_REGEX.match(sha.lower()):
                raise CatalogConfigurationError(f"Direct model '{model_key}' has malformed SHA-256 digest: '{sha}'", item)

            if sha.lower() == EMPTY_FILE_SHA256:
                raise CatalogConfigurationError(
                    f"Direct model '{model_key}' cannot use empty-file SHA-256 '{EMPTY_FILE_SHA256}'", item
                )
        elif fmt == ModelFormat.OLLAMA:
            if not item.get("ollama_name"):
                raise CatalogConfigurationError(f"Ollama model '{model_key}' must define 'ollama_name'", item)
        else:
            raise CatalogConfigurationError(f"Unsupported model format: '{fmt}' in '{model_key}'", item)

        spec = CatalogModelSpec.model_validate(item)
        validated.append(spec)

    return validated


# Validate static catalog at module import time (fail closed)
_FROZEN_CATALOG: List[CatalogModelSpec] = validate_catalog(RAW_CATALOG)


def get_curated_catalog() -> List[CatalogModelSpec]:
    """Returns the immutable validated catalog specifications."""
    return list(_FROZEN_CATALOG)


def get_catalog_entry(model_key: str) -> CatalogModelSpec:
    """Finds a catalog entry by its unique model_key or raises CatalogConfigurationError."""
    for spec in _FROZEN_CATALOG:
        if spec.model_key == model_key:
            return spec
    raise CatalogConfigurationError(f"Model key '{model_key}' not found in catalog")


def compute_catalog_compatibility(
    specs: List[CatalogModelSpec],
    hardware: HardwareProfile,
) -> List[CatalogModelSpec]:
    """
    Computes deterministic resource compatibility and starter recommendations
    based on host hardware inspection.
    """
    total_ram_mb = hardware.memory.total_mb
    vram_mb = hardware.gpu.vram_mb if hardware.gpu else 0
    tier = hardware.hardware_tier

    enriched: List[CatalogModelSpec] = []
    for s in specs:
        spec_copy = s.model_copy()

        # 1. Resource Compatibility
        if spec_copy.ram_required_mb > total_ram_mb:
            spec_copy.is_compatible = False
            spec_copy.compatibility_reason = (
                f"Requires at least {spec_copy.ram_required_mb} MB RAM (system has {total_ram_mb} MB)"
            )
        elif spec_copy.vram_recommended_mb > vram_mb and vram_mb > 0:
            spec_copy.is_compatible = True
            spec_copy.compatibility_reason = (
                "Supported via CPU/RAM; GPU VRAM insufficient for full acceleration"
            )
        else:
            spec_copy.is_compatible = True
            spec_copy.compatibility_reason = "Fully compatible with host hardware resources"

        # 2. Starter Recommendation Policy
        is_rec = False
        if spec_copy.is_compatible:
            if tier == HardwareTier.LOW:
                if "1.5b" in spec_copy.model_id.lower() or spec_copy.category == ModelCategory.EMBEDDING:
                    is_rec = True
            elif tier == HardwareTier.MEDIUM:
                if "3b" in spec_copy.model_id.lower() or spec_copy.category == ModelCategory.EMBEDDING:
                    is_rec = True
            else:  # HIGH / ENTHUSIAST
                if "3b" in spec_copy.model_id.lower() or "7b" in spec_copy.model_id.lower() or spec_copy.category == ModelCategory.EMBEDDING:
                    is_rec = True

        spec_copy.recommended = is_rec
        enriched.append(spec_copy)

    return enriched
