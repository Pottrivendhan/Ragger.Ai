"""
ModelManagerService: Central orchestrator for Phase 9 Local AI Model Manager.
Manages hardware profiling, catalog compatibility, direct downloads, Ollama pulls,
installed model inventory reconciliation, deletion dependency protection, and role activation.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .catalog import (
    compute_catalog_compatibility,
    get_catalog_entry,
    get_curated_catalog,
)
from .downloader import DirectDownloader
from .exceptions import (
    ModelInUseError,
    ModelNotFoundError,
    ModelRoleMismatchError,
)
from .hardware import get_hardware_profile
from .models import (
    ActivateModelResponse,
    CatalogModelSpec,
    DownloadProgress,
    HardwareProfile,
    InstalledModelInfo,
    InstalledStatus,
    ModelCategory,
    ModelFormat,
    OllamaStatusResponse,
)
from .ollama_manager import OllamaManager


class ModelManagerService:
    """Facade coordinating local model lifecycles across direct weights and Ollama daemon."""

    def __init__(
        self,
        storage_dir: Path,
        workspace_dir: Path,
        ollama_base_url: str = "http://127.0.0.1:11434",
    ):
        self.storage_dir = Path(storage_dir)
        self.workspace_dir = Path(workspace_dir)
        self.models_dir = self.storage_dir / "models"
        self.models_dir.mkdir(parents=True, exist_ok=True)

        self.installed_file = self.models_dir / "installed_direct.json"

        # Downloader & Ollama manager instances
        self.direct_downloader = DirectDownloader(
            storage_dir=self.models_dir,
            on_completed=self._on_direct_download_completed,
        )
        self.ollama_manager = OllamaManager(
            base_url=ollama_base_url,
            on_completed=self._on_ollama_pull_completed,
        )

        # Reconcile inventory on startup
        self._reconcile_direct_inventory()

    # -------------------------------------------------------------------------
    # Hardware & Catalog Queries
    # -------------------------------------------------------------------------

    def get_hardware(self, refresh: bool = False) -> HardwareProfile:
        """Returns host hardware capabilities and tier, using 5-minute TTL cache unless refresh=True."""
        return get_hardware_profile(refresh=refresh, storage_path=self.models_dir)

    def get_catalog(self, refresh_hardware: bool = False) -> List[CatalogModelSpec]:
        """Returns the immutable catalog enriched with host hardware compatibility and recommendations."""
        hw = self.get_hardware(refresh=refresh_hardware)
        specs = get_curated_catalog()
        compat_specs = compute_catalog_compatibility(specs, hw)
        result: List[CatalogModelSpec] = []
        for spec in compat_specs:
            if spec.format in (ModelFormat.GGUF, ModelFormat.ONNX):
                target_filename = Path(spec.runtime_model_ref).name
                canonical_path = (self.models_dir / spec.category.value / target_filename).resolve()
                spec_dict = spec.model_dump()
                spec_dict["runtime_model_ref"] = str(canonical_path)
                result.append(CatalogModelSpec.model_validate(spec_dict))
            else:
                result.append(spec)
        return result

    async def get_ollama_status(self) -> OllamaStatusResponse:
        """Returns local Ollama daemon connection diagnostics."""
        return await self.ollama_manager.check_status()

    # -------------------------------------------------------------------------
    # Installed Inventory Management
    # -------------------------------------------------------------------------

    def _load_direct_records(self) -> Dict[str, dict]:
        if not self.installed_file.exists():
            return {}
        try:
            with open(self.installed_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_direct_records(self, records: Dict[str, dict]) -> None:
        tmp_file = self.installed_file.with_name(f"{self.installed_file.name}.tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, self.installed_file)

    def _reconcile_direct_inventory(self) -> None:
        """Startup check: verifies existence and size of recorded direct model files."""
        records = self._load_direct_records()
        changed = False

        for key, rec in records.items():
            file_path_str = rec.get("file_path") or rec.get("runtime_model_ref")
            if not file_path_str:
                rec["status"] = InstalledStatus.MISSING.value
                changed = True
                continue

            fpath = Path(file_path_str)
            if not fpath.is_absolute():
                fpath = self.models_dir / fpath
            fpath = fpath.resolve()

            # Security verification: path must be strictly inside self.models_dir without ../ traversal
            try:
                fpath.relative_to(self.models_dir.resolve())
            except ValueError:
                rec["status"] = InstalledStatus.CORRUPTED.value
                changed = True
                continue

            canonical_str = str(fpath)
            if rec.get("file_path") != canonical_str or rec.get("runtime_model_ref") != canonical_str:
                rec["file_path"] = canonical_str
                rec["runtime_model_ref"] = canonical_str
                changed = True

            if not fpath.exists():
                rec["status"] = InstalledStatus.MISSING.value
                changed = True
            elif fpath.stat().st_size != rec.get("size_bytes", 0):
                rec["status"] = InstalledStatus.CORRUPTED.value
                changed = True
            else:
                rec["status"] = InstalledStatus.READY.value

        if changed:
            self._save_direct_records(records)

    async def list_installed_models(self) -> List[InstalledModelInfo]:
        """Returns a unified inventory of all installed models (Direct weights + Ollama models)."""
        installed: List[InstalledModelInfo] = []

        # 1. Direct models from reconciled inventory
        records = self._load_direct_records()
        for key, rec in records.items():
            status = InstalledStatus(rec.get("status", "ready"))
            file_path_raw = rec.get("file_path") or rec.get("runtime_model_ref") or ""
            fpath = Path(file_path_raw)
            if not fpath.is_absolute():
                fpath = self.models_dir / fpath
            fpath = fpath.resolve()

            # Security check: verify fpath is inside self.models_dir and no ../ traversal escape
            try:
                fpath.relative_to(self.models_dir.resolve())
            except ValueError:
                status = InstalledStatus.CORRUPTED

            canonical_ref = str(fpath)

            installed.append(
                InstalledModelInfo(
                    model_key=key,
                    model_id=rec.get("model_id", key),
                    format=ModelFormat(rec.get("format", "gguf")),
                    revision=rec.get("revision", "v1"),
                    category=ModelCategory(rec.get("category", "generation")),
                    size_bytes=rec.get("size_bytes", 0),
                    sha256=rec.get("sha256"),
                    ollama_name=None,
                    ollama_digest=None,
                    file_path=canonical_ref,
                    installed_at=rec.get("installed_at", datetime.now(timezone.utc).isoformat()),
                    status=status,
                    runtime_model_ref=canonical_ref,
                )
            )

        # 2. Live models from Ollama daemon
        ollama_models = await self.ollama_manager.list_models()
        installed.extend(ollama_models)

        return installed

    # -------------------------------------------------------------------------
    # Download & Pull Operations
    # -------------------------------------------------------------------------

    async def download_model(self, model_key: str) -> DownloadProgress:
        """Initiates download or pull for the specified catalog model_key."""
        spec = self._resolve_catalog_spec(model_key)

        if spec.format == ModelFormat.OLLAMA:
            return await self.ollama_manager.pull_model(spec)
        else:
            return await self.direct_downloader.start_download(spec)

    async def pause_download(self, model_key: str) -> dict:
        """Pauses an active direct file download with fsync buffer flush."""
        spec = self._resolve_catalog_spec(model_key)
        if spec.format == ModelFormat.OLLAMA:
            return {"status": "pause_not_supported_for_ollama", "model_key": model_key}
        return await self.direct_downloader.pause_download(model_key)

    async def resume_download(self, model_key: str) -> DownloadProgress:
        """Resumes a paused direct download."""
        spec = self._resolve_catalog_spec(model_key)
        if spec.format == ModelFormat.OLLAMA:
            return await self.ollama_manager.pull_model(spec)
        return await self.direct_downloader.resume_download(spec)

    async def cancel_download(self, model_key: str) -> dict:
        """Cancels an active direct download or Ollama pull."""
        spec = self._resolve_catalog_spec(model_key)
        if spec.format == ModelFormat.OLLAMA:
            return await self.ollama_manager.cancel_pull(model_key)
        return await self.direct_downloader.cancel_download(model_key)

    def get_download_progress(self, model_key: str) -> Optional[DownloadProgress]:
        """Returns observable telemetry for a download or pull in progress."""
        progress = self.direct_downloader.get_progress(model_key)
        if progress:
            return progress
        return self.ollama_manager.get_progress(model_key)

    # -------------------------------------------------------------------------
    # Deletion with Dependency Protection (MODEL_IN_USE)
    # -------------------------------------------------------------------------

    async def delete_model(self, model_key: str) -> dict:
        """
        Safely removes model from disk or Ollama daemon.
        Fail-closed: raises HTTP 409 ModelInUseError if model is referenced in active configurations.
        """
        possible_refs = {model_key, model_key.replace("ollama:", "")}
        try:
            spec = get_catalog_entry(model_key)
            possible_refs.add(spec.runtime_model_ref)
            possible_refs.add(Path(spec.runtime_model_ref).name)
        except Exception:
            pass

        records = self._load_direct_records()
        if model_key in records:
            rec = records[model_key]
            if rec.get("runtime_model_ref"):
                possible_refs.add(rec["runtime_model_ref"])
                possible_refs.add(Path(rec["runtime_model_ref"]).name)
            if rec.get("file_path"):
                possible_refs.add(rec["file_path"])
                possible_refs.add(Path(rec["file_path"]).name)

        # 1. Inspect active configurations across all workspaces
        referencing_configs: Dict[str, List[str]] = {}
        self._check_configuration_references(possible_refs, referencing_configs)

        if referencing_configs:
            raise ModelInUseError(model_key, referencing_configs)

        # 2. Proceed with deletion
        if model_key.startswith("ollama:"):
            ollama_name = model_key.replace("ollama:", "")
            deleted = await self.ollama_manager.delete_model(ollama_name)
            return {"deleted": deleted, "model_key": model_key}
        else:
            if model_key in records:
                rec = records.pop(model_key)
                fpath_str = rec.get("file_path")
                if fpath_str:
                    fpath = Path(fpath_str)
                    if not fpath.is_absolute():
                        fpath = self.models_dir / fpath
                    if fpath.exists():
                        fpath.unlink()
                self._save_direct_records(records)
                return {"deleted": True, "model_key": model_key}

        raise ModelNotFoundError(model_key)

    def _check_configuration_references(self, possible_refs: set, referencing_configs: Dict[str, List[str]]) -> None:
        """Checks generation_config.json and evaluation_config.json across workspaces for model references."""
        # Check root workspace and sub-workspaces
        candidates = [self.workspace_dir]
        workspaces_dir = self.workspace_dir / "workspaces"
        if workspaces_dir.exists():
            for sub in workspaces_dir.iterdir():
                if sub.is_dir():
                    candidates.append(sub)

        for ws in candidates:
            ws_id = ws.name

            # Check Generation Config
            gen_cfg = ws / "generation_config.json"
            if gen_cfg.exists():
                try:
                    with open(gen_cfg, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    mod_name = data.get("model_name", "")
                    if mod_name in possible_refs or Path(mod_name).name in possible_refs:
                        referencing_configs.setdefault(ws_id, []).append("generation_config.json")
                except Exception:
                    pass

            # Check Evaluation Config
            eval_cfg = ws / "evaluation_config.json"
            if eval_cfg.exists():
                try:
                    with open(eval_cfg, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    judge_name = data.get("judge_model_name", "")
                    if judge_name in possible_refs or Path(judge_name).name in possible_refs:
                        referencing_configs.setdefault(ws_id, []).append("evaluation_config.json")
                except Exception:
                    pass

    # -------------------------------------------------------------------------
    # Explicit Activation & Role Verification (Install != Activate)
    # -------------------------------------------------------------------------

    async def activate_model(
        self,
        model_key: str,
        role: str,
        workspace_id: str = "default",
    ) -> ActivateModelResponse:
        """
        Explicitly updates runtime configuration for role ('generation' or 'evaluation')
        after strictly validating model category compatibility (HTTP 422).
        """
        spec = self._resolve_catalog_spec(model_key)

        # 1. Role / Category Validation
        if role == "generation":
            if spec.category != ModelCategory.GENERATION:
                raise ModelRoleMismatchError(model_key, spec.category.value, role)
        elif role == "evaluation":
            if spec.category != ModelCategory.JUDGE:
                raise ModelRoleMismatchError(model_key, spec.category.value, role)
        else:
            raise ModelRoleMismatchError(model_key, spec.category.value, role)

        # 2. Verify model is installed and ready
        installed_models = await self.list_installed_models()
        matching = [m for m in installed_models if m.model_key == model_key and m.status == InstalledStatus.READY]
        if not matching:
            raise ModelNotFoundError(model_key)

        installed_info = matching[0]
        runtime_ref = installed_info.runtime_model_ref

        # 3. Determine target workspace path
        target_ws_dir = self.workspace_dir
        if workspace_id != "default":
            sub_ws = self.workspace_dir / "workspaces" / workspace_id
            if sub_ws.exists():
                target_ws_dir = sub_ws

        # 4. Atomic Configuration Update
        if role == "generation":
            cfg_file = target_ws_dir / "generation_config.json"
            existing = {}
            if cfg_file.exists():
                try:
                    with open(cfg_file, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                except Exception:
                    pass

            provider = "ollama" if spec.format == ModelFormat.OLLAMA else "local_gguf"
            existing["provider"] = provider
            existing["model_name"] = runtime_ref
            if "temperature" not in existing:
                existing["temperature"] = 0.1
            if "max_tokens" not in existing:
                existing["max_tokens"] = 1024

            self._write_json_atomic(cfg_file, existing)
            return ActivateModelResponse(
                model_key=model_key,
                role=role,
                workspace_id=workspace_id,
                runtime_model_ref=runtime_ref,
                updated_config_file="generation_config.json",
                updated_config=existing,
            )

        else:  # role == "evaluation"
            cfg_file = target_ws_dir / "evaluation_config.json"
            existing = {}
            if cfg_file.exists():
                try:
                    with open(cfg_file, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                except Exception:
                    pass

            provider = "ollama" if spec.format == ModelFormat.OLLAMA else "local_gguf"
            existing["judge_provider"] = provider
            existing["judge_model_name"] = runtime_ref
            if "temperature" not in existing:
                existing["temperature"] = 0.0
            if "max_tokens" not in existing:
                existing["max_tokens"] = 1024
            if "default_sample_size" not in existing:
                existing["default_sample_size"] = 10
            if "sampling_seed" not in existing:
                existing["sampling_seed"] = 42
            if "retrieval_top_k" not in existing:
                existing["retrieval_top_k"] = 5

            self._write_json_atomic(cfg_file, existing)
            return ActivateModelResponse(
                model_key=model_key,
                role=role,
                workspace_id=workspace_id,
                runtime_model_ref=runtime_ref,
                updated_config_file="evaluation_config.json",
                updated_config=existing,
            )

    def _write_json_atomic(self, target_file: Path, data: dict) -> None:
        tmp_file = target_file.with_name(f"{target_file.name}.tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, target_file)

    def _resolve_catalog_spec(self, model_key: str) -> CatalogModelSpec:
        try:
            return get_catalog_entry(model_key)
        except Exception:
            raise ModelNotFoundError(model_key)

    def _on_direct_download_completed(self, spec: CatalogModelSpec, target_path: Path) -> None:
        """Callback invoked when direct downloader finishes SHA-256 verification and rename."""
        canonical_path = target_path.resolve()
        try:
            canonical_path.relative_to(self.models_dir.resolve())
        except ValueError:
            raise ValueError(f"Target path {canonical_path} escaped models_dir {self.models_dir}")
        canonical_str = str(canonical_path)
        records = self._load_direct_records()
        records[spec.model_key] = {
            "model_key": spec.model_key,
            "model_id": spec.model_id,
            "format": spec.format.value,
            "revision": spec.revision,
            "category": spec.category.value,
            "size_bytes": spec.size_bytes,
            "sha256": spec.sha256,
            "file_path": canonical_str,
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "status": InstalledStatus.READY.value,
            "runtime_model_ref": canonical_str,
        }
        self._save_direct_records(records)

    def _on_ollama_pull_completed(self, spec: CatalogModelSpec) -> None:
        """Callback invoked when Ollama pull successfully finishes."""
        pass
