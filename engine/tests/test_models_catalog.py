"""
Unit tests for Phase 9 Model Catalog Invariants, Identity, and Fail-Closed Validation.
"""

import pytest
from ragger_engine.models.catalog import (
    EMPTY_FILE_SHA256,
    get_curated_catalog,
    validate_catalog,
)
from ragger_engine.models.exceptions import CatalogConfigurationError
from ragger_engine.models.models import ModelCategory, ModelFormat


def test_catalog_identity_distinct_keys_for_different_format_and_revision():
    """Verifies that the same model_id with different format or revision produces distinct model_keys."""
    catalog = get_curated_catalog()
    model_keys = [spec.model_key for spec in catalog]

    # Verify all catalog keys are unique
    assert len(model_keys) == len(set(model_keys))

    # Check GGUF vs Ollama distinctions
    qwen_gguf = [s for s in catalog if s.model_key == "qwen2.5-1.5b-instruct:gguf:q4_k_m-v1"]
    qwen_ollama = [s for s in catalog if s.model_key == "ollama:qwen2.5:1.5b"]

    assert len(qwen_gguf) == 1
    assert len(qwen_ollama) == 1
    assert qwen_gguf[0].model_key != qwen_ollama[0].model_key


def test_catalog_fail_closed_on_missing_sha256():
    """Verifies that direct models without a verified sha256 fail closed on startup."""
    invalid_catalog = [
        {
            "model_id": "test-model",
            "model_key": "test-model:gguf:v1",
            "format": ModelFormat.GGUF,
            "revision": "v1",
            "category": ModelCategory.GENERATION,
            "download_url": "https://example.com/model.gguf",
            "size_bytes": 1000,
            "sha256": None,  # Missing!
            "parameter_size": "1B",
            "ram_required_mb": 1000,
            "vram_recommended_mb": 1000,
            "context_length": 2048,
            "description": "Test",
            "runtime_model_ref": "models/test.gguf",
        }
    ]

    with pytest.raises(CatalogConfigurationError) as exc_info:
        validate_catalog(invalid_catalog)
    assert "malformed SHA-256 digest" in str(exc_info.value)


def test_catalog_fail_closed_on_empty_file_sha256():
    """Verifies that direct models configured with the well-known empty-file hash fail closed."""
    invalid_catalog = [
        {
            "model_id": "test-empty",
            "model_key": "test-empty:gguf:v1",
            "format": ModelFormat.GGUF,
            "revision": "v1",
            "category": ModelCategory.GENERATION,
            "download_url": "https://example.com/model.gguf",
            "size_bytes": 1000,
            "sha256": EMPTY_FILE_SHA256,  # Forbidden placeholder!
            "parameter_size": "1B",
            "ram_required_mb": 1000,
            "vram_recommended_mb": 1000,
            "context_length": 2048,
            "description": "Test",
            "runtime_model_ref": "models/test.gguf",
        }
    ]

    with pytest.raises(CatalogConfigurationError) as exc_info:
        validate_catalog(invalid_catalog)
    assert "cannot use empty-file SHA-256" in str(exc_info.value)


def test_catalog_fail_closed_on_insecure_http_url():
    """Verifies that direct models with non-HTTPS URLs fail closed."""
    invalid_catalog = [
        {
            "model_id": "test-insecure",
            "model_key": "test-insecure:gguf:v1",
            "format": ModelFormat.GGUF,
            "revision": "v1",
            "category": ModelCategory.GENERATION,
            "download_url": "http://insecure.com/model.gguf",  # Insecure HTTP
            "size_bytes": 1000,
            "sha256": "1" * 64,
            "parameter_size": "1B",
            "ram_required_mb": 1000,
            "vram_recommended_mb": 1000,
            "context_length": 2048,
            "description": "Test",
            "runtime_model_ref": "models/test.gguf",
        }
    ]

    with pytest.raises(CatalogConfigurationError) as exc_info:
        validate_catalog(invalid_catalog)
    assert "must have an HTTPS download URL" in str(exc_info.value)


def test_catalog_fail_closed_on_duplicate_model_key():
    """Verifies that duplicate model keys fail closed on startup."""
    invalid_catalog = [
        {
            "model_id": "dup",
            "model_key": "duplicate:key",
            "format": ModelFormat.OLLAMA,
            "revision": "latest",
            "category": ModelCategory.GENERATION,
            "size_bytes": 1000,
            "parameter_size": "1B",
            "ram_required_mb": 1000,
            "vram_recommended_mb": 1000,
            "context_length": 2048,
            "description": "Dup 1",
            "ollama_name": "dup",
            "runtime_model_ref": "dup",
        },
        {
            "model_id": "dup2",
            "model_key": "duplicate:key",  # Duplicate!
            "format": ModelFormat.OLLAMA,
            "revision": "latest",
            "category": ModelCategory.GENERATION,
            "size_bytes": 1000,
            "parameter_size": "1B",
            "ram_required_mb": 1000,
            "vram_recommended_mb": 1000,
            "context_length": 2048,
            "description": "Dup 2",
            "ollama_name": "dup2",
            "runtime_model_ref": "dup2",
        },
    ]

    with pytest.raises(CatalogConfigurationError) as exc_info:
        validate_catalog(invalid_catalog)
    assert "Duplicate 'model_key' detected" in str(exc_info.value)
