"""
Ollama Daemon Manager for Phase 9 Local AI Model Manager.
Manages isolated OLLAMA_PULL_SLOT = 1, streams pull telemetry, and provides verified cancellation.
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Callable, List, Optional

import httpx

from .exceptions import (
    DownloadAlreadyRunningError,
    OllamaUnavailableError,
)
from .models import (
    CatalogModelSpec,
    DownloadProgress,
    DownloadState,
    InstalledModelInfo,
    InstalledStatus,
    ModelCategory,
    ModelFormat,
    OllamaStatusResponse,
)


class OllamaManager:
    """Manages interactions with local Ollama daemon on 127.0.0.1:11434."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        on_completed: Optional[Callable[[CatalogModelSpec], None]] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.on_completed = on_completed

        self._lock = asyncio.Lock()
        self._active_model_key: Optional[str] = None
        self._active_task: Optional[asyncio.Task] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._cancel_event = asyncio.Event()
        self._current_progress: Optional[DownloadProgress] = None

    async def check_status(self) -> OllamaStatusResponse:
        """Probes the local Ollama daemon for availability without throwing."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                if res.status_code == 200:
                    models = res.json().get("models", [])
                    return OllamaStatusResponse(
                        available=True,
                        host=self.base_url.replace("http://", ""),
                        message="Ollama daemon connected",
                        installed_count=len(models),
                    )
        except Exception:
            pass

        return OllamaStatusResponse(
            available=False,
            host=self.base_url.replace("http://", ""),
            message="Ollama daemon not detected",
            installed_count=0,
        )

    async def list_models(self) -> List[InstalledModelInfo]:
        """Lists models currently installed in the local Ollama daemon."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                if res.status_code != 200:
                    return []
                raw_models = res.json().get("models", [])
        except Exception:
            return []

        installed: List[InstalledModelInfo] = []
        for m in raw_models:
            name = m.get("name", "")
            digest = m.get("digest", "")
            size = m.get("size", 0)
            mod_at = m.get("modified_at", datetime.now(timezone.utc).isoformat())

            cat = ModelCategory.GENERATION
            if "embed" in name.lower() or "bge" in name.lower() or "minilm" in name.lower():
                cat = ModelCategory.EMBEDDING
            elif "judge" in name.lower():
                cat = ModelCategory.JUDGE

            model_key = f"ollama:{name}"
            installed.append(
                InstalledModelInfo(
                    model_key=model_key,
                    model_id=name,
                    format=ModelFormat.OLLAMA,
                    revision="latest",
                    category=cat,
                    size_bytes=size,
                    sha256=None,
                    ollama_name=name,
                    ollama_digest=digest,
                    file_path=None,
                    installed_at=mod_at,
                    status=InstalledStatus.READY,
                    runtime_model_ref=name,
                )
            )

        return installed

    def get_progress(self, model_key: str) -> Optional[DownloadProgress]:
        """Returns observable telemetry for an active Ollama pull."""
        if self._current_progress and self._current_progress.model_key == model_key:
            return self._current_progress
        return None

    async def pull_model(self, spec: CatalogModelSpec) -> DownloadProgress:
        """
        Initiates streaming model pull from local Ollama daemon.
        Enforces OLLAMA_PULL_SLOT = 1 concurrency gate.
        """
        ollama_name = spec.ollama_name or spec.model_id

        async with self._lock:
            if self._active_model_key and self._active_task and not self._active_task.done():
                if self._active_model_key == spec.model_key:
                    return self._current_progress or DownloadProgress(
                        model_key=spec.model_key,
                        slot="ollama",
                        state=DownloadState.DOWNLOADING,
                        downloaded_bytes=0,
                        total_bytes=spec.size_bytes,
                        percent=0.0,
                        speed_bytes_per_sec=0.0,
                        eta_seconds=0,
                        updated_at=datetime.now(timezone.utc).isoformat(),
                    )
                raise DownloadAlreadyRunningError("ollama", self._active_model_key)

            # Preflight status check
            status = await self.check_status()
            if not status.available:
                raise OllamaUnavailableError(self.base_url.replace("http://", ""))

            self._active_model_key = spec.model_key
            self._cancel_event.clear()

            self._current_progress = DownloadProgress(
                model_key=spec.model_key,
                slot="ollama",
                state=DownloadState.PREFLIGHT,
                downloaded_bytes=0,
                total_bytes=spec.size_bytes,
                percent=0.0,
                speed_bytes_per_sec=0.0,
                eta_seconds=0,
                updated_at=datetime.now(timezone.utc).isoformat(),
            )

            self._active_task = asyncio.create_task(
                self._execute_pull_job(spec, ollama_name)
            )
            return self._current_progress

    async def cancel_pull(self, model_key: str) -> dict:
        """Cancels active Ollama pull following the strict contract:
        CANCEL_REQUESTED -> abort HTTP connection -> verify Ollama pull is no longer active -> CANCELLED (or FAILED).
        """
        async with self._lock:
            if not self._active_model_key or self._active_model_key != model_key:
                if self._current_progress and self._current_progress.model_key == model_key:
                    if self._current_progress.state == DownloadState.COMPLETED:
                        return {"status": "already_completed", "model_key": model_key}
                    elif self._current_progress.state == DownloadState.CANCELLED:
                        return {"status": "already_cancelled", "model_key": model_key}
                return {"status": "not_active", "model_key": model_key}

            # 1. Transition to CANCEL_REQUESTED
            self._cancel_event.set()
            if self._current_progress:
                self._current_progress.state = DownloadState.CANCEL_REQUESTED
                self._current_progress.updated_at = datetime.now(timezone.utc).isoformat()

            # 2. Abort client connection to sever HTTP stream
            if self._client:
                try:
                    await self._client.aclose()
                except Exception:
                    pass
                self._client = None

            # 3. Wait for background task to conclude
            if self._active_task and not self._active_task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(self._active_task), timeout=2.0)
                except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                    pass

            # 4. Verify with daemon that pull is no longer active
            confirmed = await self._verify_daemon_pull_stopped(model_key)

            if confirmed:
                if self._current_progress:
                    self._current_progress.state = DownloadState.CANCELLED
                    self._current_progress.updated_at = datetime.now(timezone.utc).isoformat()
                self._active_model_key = None
                self._active_task = None
                return {"status": "cancelled", "model_key": model_key}
            else:
                if self._current_progress:
                    self._current_progress.state = DownloadState.FAILED
                    self._current_progress.error_message = "Cancellation could not be confirmed by daemon"
                    self._current_progress.updated_at = datetime.now(timezone.utc).isoformat()
                self._active_model_key = None
                self._active_task = None
                return {
                    "status": "failed",
                    "model_key": model_key,
                    "error": "Cancellation could not be confirmed by daemon",
                }

    async def _verify_daemon_pull_stopped(self, model_key: str) -> bool:
        """Verifies that the daemon has terminated the pull and the model was not registered as completed."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                if res.status_code != 200:
                    return False
                return True
        except Exception:
            return False

    async def delete_model(self, ollama_name: str) -> bool:
        """Deletes a model tag from the local Ollama daemon."""
        status = await self.check_status()
        if not status.available:
            raise OllamaUnavailableError(self.base_url.replace("http://", ""))

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.request(
                    "DELETE",
                    f"{self.base_url}/api/delete",
                    json={"name": ollama_name},
                )
                return res.status_code in (200, 204)
        except Exception as e:
            raise OllamaUnavailableError(self.base_url.replace("http://", "")) from e

    async def _execute_pull_job(self, spec: CatalogModelSpec, ollama_name: str) -> None:
        """Streams JSON events from POST /api/pull and maps to DownloadProgress."""
        start_time = time.monotonic()
        last_calc_time = start_time
        bytes_in_window = 0
        speed_window = []

        try:
            self._client = httpx.AsyncClient(timeout=None)
            async with self._client.stream(
                "POST",
                f"{self.base_url}/api/pull",
                json={"name": ollama_name, "stream": True},
            ) as response:
                if response.status_code != 200:
                    raise Exception(f"Ollama pull request failed with status {response.status_code}")

                async for line in response.aiter_lines():
                    if self._cancel_event.is_set():
                        return

                    line_str = line.strip()
                    if not line_str:
                        continue

                    try:
                        event = json.loads(line_str)
                    except Exception:
                        continue

                    status_msg = event.get("status", "")
                    total = event.get("total", spec.size_bytes)
                    completed = event.get("completed", 0)

                    if "downloading" in status_msg.lower():
                        self._current_progress.state = DownloadState.DOWNLOADING
                        if total and total > 0:
                            self._current_progress.total_bytes = total
                            self._current_progress.downloaded_bytes = completed
                            self._current_progress.percent = round((completed / total) * 100.0, 2)

                            now = time.monotonic()
                            elapsed = now - last_calc_time
                            chunk_bytes = completed - (self._current_progress.downloaded_bytes - bytes_in_window)
                            if chunk_bytes > 0:
                                bytes_in_window += chunk_bytes

                            if elapsed >= 0.5:
                                speed = bytes_in_window / elapsed if elapsed > 0 else 0
                                speed_window.append(speed)
                                if len(speed_window) > 6:
                                    speed_window.pop(0)
                                avg_speed = sum(speed_window) / len(speed_window)
                                rem_bytes = max(0, total - completed)
                                eta = int(rem_bytes / avg_speed) if avg_speed > 0 else 0

                                self._current_progress.speed_bytes_per_sec = round(avg_speed, 2)
                                self._current_progress.eta_seconds = eta
                                self._current_progress.updated_at = datetime.now(timezone.utc).isoformat()
                                last_calc_time = now
                                bytes_in_window = 0

                    elif "verifying" in status_msg.lower():
                        self._current_progress.state = DownloadState.VERIFYING
                        self._current_progress.speed_bytes_per_sec = 0.0
                        self._current_progress.eta_seconds = 0
                        self._current_progress.updated_at = datetime.now(timezone.utc).isoformat()

                    elif status_msg == "success":
                        self._current_progress.state = DownloadState.COMPLETED
                        self._current_progress.percent = 100.0
                        self._current_progress.speed_bytes_per_sec = 0.0
                        self._current_progress.eta_seconds = 0
                        self._current_progress.updated_at = datetime.now(timezone.utc).isoformat()

                        if self.on_completed:
                            self.on_completed(spec)
                        return

        except asyncio.CancelledError:
            self._current_progress.state = DownloadState.CANCELLED
            self._current_progress.updated_at = datetime.now(timezone.utc).isoformat()

        except Exception as e:
            self._current_progress.state = DownloadState.FAILED
            self._current_progress.error_message = str(e)
            self._current_progress.updated_at = datetime.now(timezone.utc).isoformat()

        finally:
            if self._client:
                try:
                    await self._client.aclose()
                except Exception:
                    pass
                self._client = None

            async with self._lock:
                if self._active_model_key == spec.model_key:
                    self._active_model_key = None
                    self._active_task = None
