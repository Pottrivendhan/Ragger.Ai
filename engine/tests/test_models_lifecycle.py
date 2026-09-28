"""
Unit tests for Phase 9 Model Lifecycle: Concurrency slots, MODEL_IN_USE dependency protection,
role/category activation validation (HTTP 422), and exact config schema updates.
"""

import json
from pathlib import Path
import pytest

from ragger_engine.models.exceptions import (
    DownloadAlreadyRunningError,
    ModelInUseError,
    ModelRoleMismatchError,
)
from ragger_engine.models.models import (
    CatalogModelSpec,
    DownloadState,
    InstalledStatus,
    ModelCategory,
    ModelFormat,
)
from ragger_engine.models.service import ModelManagerService


@pytest.fixture
def service_env(tmp_path):
    storage = tmp_path / "storage"
    workspaces = tmp_path / "workspaces"
    storage.mkdir(parents=True, exist_ok=True)
    workspaces.mkdir(parents=True, exist_ok=True)
    return storage, workspaces


def test_independent_concurrency_slots(service_env):
    """Verifies that Direct and Ollama download slots operate independently without blocking each other."""
    storage, workspaces = service_env
    service = ModelManagerService(storage, workspaces)

    # Set direct download active
    service.direct_downloader._active_model_key = "direct:model:v1"
    class DummyTask:
        def done(self):
            return False
    service.direct_downloader._active_task = DummyTask()

    # Set ollama pull active
    service.ollama_manager._active_model_key = "ollama:model:v1"
    service.ollama_manager._active_task = DummyTask()

    # Attempting second direct download -> Conflict
    with pytest.raises(DownloadAlreadyRunningError) as exc1:
        spec_direct = CatalogModelSpec(
            model_id="d2",
            model_key="d2:gguf:v1",
            format=ModelFormat.GGUF,
            revision="v1",
            category=ModelCategory.GENERATION,
            download_url="https://example.com/d2.gguf",
            size_bytes=1000,
            sha256="1" * 64,
            parameter_size="1B",
            ram_required_mb=1000,
            vram_recommended_mb=1000,
            context_length=2048,
            description="d2",
            runtime_model_ref="d2.gguf",
        )
        import asyncio
        asyncio.run(service.direct_downloader.start_download(spec_direct))
    assert exc1.value.details["slot"] == "direct"

    # Attempting second ollama pull -> Conflict
    with pytest.raises(DownloadAlreadyRunningError) as exc2:
        spec_ollama = CatalogModelSpec(
            model_id="o2",
            model_key="ollama:o2",
            format=ModelFormat.OLLAMA,
            revision="latest",
            category=ModelCategory.GENERATION,
            size_bytes=1000,
            parameter_size="1B",
            ram_required_mb=1000,
            vram_recommended_mb=1000,
            context_length=2048,
            description="o2",
            ollama_name="o2",
            runtime_model_ref="o2",
        )
        asyncio.run(service.ollama_manager.pull_model(spec_ollama))
    assert exc2.value.details["slot"] == "ollama"


@pytest.mark.asyncio
async def test_activation_role_validation_rejects_mismatch_422(service_env):
    """Verifies that attempting to activate an embedding model for generation raises ModelRoleMismatchError (HTTP 422)."""
    storage, workspaces = service_env
    service = ModelManagerService(storage, workspaces)

    # bge-small-en-v1.5 is category=EMBEDDING
    with pytest.raises(ModelRoleMismatchError) as exc_info:
        await service.activate_model(
            model_key="bge-small-en-v1.5:onnx:default-v1",
            role="generation",
            workspace_id="default",
        )
    assert exc_info.value.code == "MODEL_ROLE_MISMATCH"
    assert "embedding" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_activation_updates_exact_phase7_and_phase8_schemas(service_env):
    """Verifies that activation updates exact model fields while preserving hyperparameters."""
    storage, workspaces = service_env
    service = ModelManagerService(storage, workspaces)

    # 1. Setup existing Phase 7 generation_config.json with custom hyperparameters
    gen_cfg = workspaces / "generation_config.json"
    gen_cfg.write_text(json.dumps({
        "provider": "old_provider",
        "model_name": "old_model",
        "temperature": 0.35,
        "max_tokens": 2048,
    }))

    # Mock installed direct model
    records = {
        "qwen2.5-1.5b-instruct:gguf:q4_k_m-v1": {
            "model_key": "qwen2.5-1.5b-instruct:gguf:q4_k_m-v1",
            "model_id": "qwen2.5-1.5b-instruct",
            "format": "gguf",
            "revision": "q4_k_m-v1",
            "category": "generation",
            "size_bytes": 100,
            "file_path": str(storage / "models" / "qwen.gguf"),
            "status": "ready",
            "runtime_model_ref": str(storage / "models" / "qwen.gguf"),
        }
    }
    # Create the physical file so inventory sees READY
    qf = storage / "models" / "qwen.gguf"
    qf.parent.mkdir(parents=True, exist_ok=True)
    qf.write_bytes(b"a" * 100)
    service._save_direct_records(records)

    # Activate for generation
    res = await service.activate_model(
        model_key="qwen2.5-1.5b-instruct:gguf:q4_k_m-v1",
        role="generation",
        workspace_id="default",
    )

    assert res.role == "generation"
    assert res.updated_config["provider"] == "local_gguf"
    assert res.updated_config["model_name"] == str(qf)
    assert res.updated_config["temperature"] == 0.35  # Preserved!
    assert res.updated_config["max_tokens"] == 2048   # Preserved!

    # 2. Setup existing Phase 8 evaluation_config.json
    eval_cfg = workspaces / "evaluation_config.json"
    eval_cfg.write_text(json.dumps({
        "judge_provider": "old_judge",
        "judge_model_name": "old_model",
        "temperature": 0.05,
        "max_tokens": 512,
        "default_sample_size": 15,
        "sampling_seed": 99,
        "retrieval_top_k": 7,
    }))

    judge_records = {
        "qwen2.5-1.5b-judge:gguf:q4_k_m-v1": {
            "model_key": "qwen2.5-1.5b-judge:gguf:q4_k_m-v1",
            "model_id": "qwen2.5-1.5b-judge",
            "format": "gguf",
            "revision": "q4_k_m-v1",
            "category": "judge",
            "size_bytes": 100,
            "file_path": str(storage / "models" / "judge.gguf"),
            "status": "ready",
            "runtime_model_ref": str(storage / "models" / "judge.gguf"),
        }
    }
    jf = storage / "models" / "judge.gguf"
    jf.write_bytes(b"a" * 100)
    records.update(judge_records)
    service._save_direct_records(records)

    # Activate for evaluation
    res_eval = await service.activate_model(
        model_key="qwen2.5-1.5b-judge:gguf:q4_k_m-v1",
        role="evaluation",
        workspace_id="default",
    )

    assert res_eval.role == "evaluation"
    assert res_eval.updated_config["judge_provider"] == "local_gguf"
    assert res_eval.updated_config["judge_model_name"] == str(jf)
    assert res_eval.updated_config["default_sample_size"] == 15  # Preserved!
    assert res_eval.updated_config["sampling_seed"] == 99        # Preserved!
    assert res_eval.updated_config["retrieval_top_k"] == 7       # Preserved!


@pytest.mark.asyncio
async def test_model_deletion_blocked_by_model_in_use_409(service_env):
    """Verifies that deleting an active model referenced in configuration raises ModelInUseError (HTTP 409)."""
    storage, workspaces = service_env
    service = ModelManagerService(storage, workspaces)

    # Set active model in generation_config.json
    gen_cfg = workspaces / "generation_config.json"
    gen_cfg.write_text(json.dumps({
        "provider": "ollama",
        "model_name": "llama3.2:3b",
    }))

    # Attempt to delete referenced model
    with pytest.raises(ModelInUseError) as exc_info:
        await service.delete_model("ollama:llama3.2:3b")

    assert exc_info.value.code == "MODEL_IN_USE"
    assert "referencing_configs" in exc_info.value.details


@pytest.mark.asyncio
async def test_direct_runtime_model_ref_canonical_and_invariants(service_env):
    """
    Verifies that Direct GGUF/ONNX weights strictly adhere to the contract:
    - runtime_model_ref is an absolute canonical path
    - runtime_model_ref resolves to the verified installed artifact
    - runtime_model_ref is strictly inside the models directory
    - runtime_model_ref does not contain '../' traversal components
    - relative or traversal attempts are automatically canonicalized or marked corrupted
    """
    storage, workspaces = service_env
    service = ModelManagerService(storage, workspaces)

    models_root = (storage / "models").resolve()
    gen_dir = models_root / "generation"
    gen_dir.mkdir(parents=True, exist_ok=True)

    test_file = gen_dir / "qwen2.5-1.5b-instruct_q4_k_m.gguf"
    payload = b"MOCK_MODEL_WEIGHTS_CONTENT_12345"
    test_file.write_bytes(payload)

    # 1. Provide relative path with ../ inside raw record
    traversal_record = {
        "qwen2.5-1.5b-instruct:gguf:q4_k_m-v1": {
            "model_key": "qwen2.5-1.5b-instruct:gguf:q4_k_m-v1",
            "model_id": "qwen2.5-1.5b-instruct",
            "format": "gguf",
            "revision": "q4_k_m-v1",
            "category": "generation",
            "size_bytes": len(payload),
            "file_path": "generation/../generation/qwen2.5-1.5b-instruct_q4_k_m.gguf",
            "status": "ready",
            "runtime_model_ref": "generation/../generation/qwen2.5-1.5b-instruct_q4_k_m.gguf",
        }
    }
    service._save_direct_records(traversal_record)

    # List installed models
    installed = await service.list_installed_models()
    assert len(installed) == 1
    m = installed[0]

    # Contract assertions
    ref_path = Path(m.runtime_model_ref)
    assert ref_path.is_absolute(), f"runtime_model_ref must be absolute, got: {m.runtime_model_ref}"
    assert ".." not in m.runtime_model_ref, f"runtime_model_ref must not contain traversal, got: {m.runtime_model_ref}"
    assert ref_path.resolve() == test_file.resolve(), "runtime_model_ref must resolve to verified artifact"
    assert ref_path.resolve().is_relative_to(models_root), "runtime_model_ref must be inside models root"
    assert ref_path.exists(), "runtime_model_ref must point to existing verified file"

    # 2. Activation returns canonical absolute path
    act_res = await service.activate_model(
        model_key="qwen2.5-1.5b-instruct:gguf:q4_k_m-v1",
        role="generation",
        workspace_id="default",
    )
    act_ref = Path(act_res.runtime_model_ref)
    assert act_ref.is_absolute()
    assert ".." not in act_res.runtime_model_ref
    assert act_ref.resolve() == test_file.resolve()
    assert act_ref.resolve().is_relative_to(models_root)
    assert act_res.updated_config["model_name"] == str(test_file.resolve())

    # 3. Path traversal escape attempt outside models root is marked CORRUPTED
    malicious_record = {
        "malicious:gguf:v1": {
            "model_key": "malicious:gguf:v1",
            "model_id": "malicious",
            "format": "gguf",
            "revision": "v1",
            "category": "generation",
            "size_bytes": 100,
            "file_path": "../../Windows/System32/drivers/etc/hosts",
            "status": "ready",
            "runtime_model_ref": "../../Windows/System32/drivers/etc/hosts",
        }
    }
    service._save_direct_records(malicious_record)
    service._reconcile_direct_inventory()
    records = service._load_direct_records()
    assert records["malicious:gguf:v1"]["status"] == "corrupted"

