"""
Unit tests for Phase 9 Ollama Manager: Offline detection, tag parsing, pull progress, and cancellation.
"""

import asyncio
import json
import pytest
import httpx

from ragger_engine.models.models import (
    CatalogModelSpec,
    DownloadState,
    InstalledStatus,
    ModelCategory,
    ModelFormat,
)
from ragger_engine.models.ollama_manager import OllamaManager


@pytest.mark.asyncio
async def test_ollama_status_offline_probe():
    """Verifies that offline daemon probe returns available=False without throwing exceptions."""
    # Point to a closed port
    manager = OllamaManager(base_url="http://127.0.0.1:59999")
    status = await manager.check_status()

    assert not status.available
    assert status.installed_count == 0
    assert "not detected" in status.message.lower()


@pytest.mark.asyncio
async def test_ollama_list_models_parsing():
    """Verifies that Ollama /api/tags JSON output is correctly mapped to InstalledModelInfo."""
    manager = OllamaManager(base_url="http://127.0.0.1:11434")

    mock_response = {
        "models": [
            {
                "name": "llama3.2:3b",
                "digest": "a80c46fd934c28bb98",
                "size": 2019000000,
                "modified_at": "2026-09-18T10:00:00Z",
            },
            {
                "name": "bge-small-en:latest",
                "digest": "f789abc1234",
                "size": 133400000,
                "modified_at": "2026-09-18T10:05:00Z",
            },
        ]
    }

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        async def get(self, url):
            class Resp:
                status_code = 200
                def json(self):
                    return mock_response
            return Resp()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    import httpx
    ollama_module = __import__("ragger_engine.models.ollama_manager", fromlist=["httpx"])
    ollama_module.httpx.AsyncClient = MockClient

    models = await manager.list_models()
    assert len(models) == 2

    m1 = models[0]
    assert m1.model_key == "ollama:llama3.2:3b"
    assert m1.ollama_name == "llama3.2:3b"
    assert m1.ollama_digest == "a80c46fd934c28bb98"
    assert m1.size_bytes == 2019000000
    assert m1.category == ModelCategory.GENERATION
    assert m1.status == InstalledStatus.READY

    m2 = models[1]
    assert m2.model_key == "ollama:bge-small-en:latest"
    assert m2.category == ModelCategory.EMBEDDING


@pytest.mark.asyncio
async def test_ollama_pull_progress_streaming():
    """Verifies streaming event mapping from Ollama daemon to DownloadProgress."""
    manager = OllamaManager(base_url="http://127.0.0.1:11434")

    spec = CatalogModelSpec(
        model_id="llama3.2:3b",
        model_key="ollama:llama3.2:3b",
        format=ModelFormat.OLLAMA,
        revision="latest",
        category=ModelCategory.GENERATION,
        download_url=None,
        size_bytes=2000,
        sha256=None,
        parameter_size="3.2B",
        ram_required_mb=4096,
        vram_recommended_mb=4096,
        context_length=8192,
        description="Test",
        ollama_name="llama3.2:3b",
        runtime_model_ref="llama3.2:3b",
    )

    events = [
        json.dumps({"status": "pulling manifest"}),
        json.dumps({"status": "downloading", "completed": 1000, "total": 2000}),
        json.dumps({"status": "verifying sha256"}),
        json.dumps({"status": "success"}),
    ]

    class MockStreamResp:
        status_code = 200

        async def aiter_lines(self):
            for e in events:
                yield e

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        def stream(self, method, url, json=None):
            return MockStreamResp()

        async def aclose(self):
            pass

        async def get(self, url):
            class R:
                status_code = 200
                def json(self):
                    return {"models": []}
            return R()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    ollama_module = __import__("ragger_engine.models.ollama_manager", fromlist=["httpx"])
    ollama_module.httpx.AsyncClient = MockClient

    progress = await manager.pull_model(spec)
    await manager._active_task

    assert manager._current_progress.state == DownloadState.COMPLETED
    assert manager._current_progress.percent == 100.0


@pytest.mark.asyncio
async def test_ollama_cancellation_confirmed_by_daemon():
    """
    Verifies that pull cancellation:
    1. Sets CANCEL_REQUESTED
    2. Aborts the client HTTP connection
    3. Confirms with daemon that pull is terminated
    4. Transitions strictly to CANCELLED state
    """
    manager = OllamaManager(base_url="http://127.0.0.1:11434")

    spec = CatalogModelSpec(
        model_id="llama3.2:3b",
        model_key="ollama:llama3.2:3b",
        format=ModelFormat.OLLAMA,
        revision="latest",
        category=ModelCategory.GENERATION,
        size_bytes=2000,
        parameter_size="3.2B",
        ram_required_mb=4096,
        vram_recommended_mb=4096,
        context_length=8192,
        description="Test",
        ollama_name="llama3.2:3b",
        runtime_model_ref="llama3.2:3b",
    )

    closed = False

    class MockLongStream:
        status_code = 200

        async def aiter_lines(self):
            while True:
                await asyncio.sleep(0.01)
                yield json.dumps({"status": "downloading", "completed": 500, "total": 2000})

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        def stream(self, method, url, json=None):
            return MockLongStream()

        async def aclose(self):
            nonlocal closed
            closed = True

        async def get(self, url):
            class R:
                status_code = 200
                def json(self):
                    return {"models": []}
            return R()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    ollama_module = __import__("ragger_engine.models.ollama_manager", fromlist=["httpx"])
    ollama_module.httpx.AsyncClient = MockClient

    # Start pull
    await manager.pull_model(spec)
    await asyncio.sleep(0.02)

    # Cancel pull
    res = await manager.cancel_pull(spec.model_key)

    assert closed is True, "HTTP stream client must be aborted on cancel"
    assert res["status"] == "cancelled"
    assert manager._current_progress.state == DownloadState.CANCELLED
    assert manager._active_model_key is None


@pytest.mark.asyncio
async def test_ollama_cancellation_unconfirmed_fails_closed():
    """
    Verifies that if the Ollama daemon cannot confirm pull termination (e.g. probe fails),
    cancellation fails closed:
    - Transitions to FAILED (not CANCELLED)
    - Error message is exactly "Cancellation could not be confirmed by daemon"
    """
    manager = OllamaManager(base_url="http://127.0.0.1:11434")

    spec = CatalogModelSpec(
        model_id="llama3.2:3b",
        model_key="ollama:llama3.2:3b",
        format=ModelFormat.OLLAMA,
        revision="latest",
        category=ModelCategory.GENERATION,
        size_bytes=2000,
        parameter_size="3.2B",
        ram_required_mb=4096,
        vram_recommended_mb=4096,
        context_length=8192,
        description="Test",
        ollama_name="llama3.2:3b",
        runtime_model_ref="llama3.2:3b",
    )

    class MockLongStream:
        status_code = 200

        async def aiter_lines(self):
            while True:
                await asyncio.sleep(0.01)
                yield json.dumps({"status": "downloading", "completed": 500, "total": 2000})

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    get_call_count = 0

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        def stream(self, method, url, json=None):
            return MockLongStream()

        async def aclose(self):
            pass

        async def get(self, url):
            nonlocal get_call_count
            get_call_count += 1
            if get_call_count == 1:
                # Preflight check_status returns available=True
                class R1:
                    status_code = 200
                    def json(self):
                        return {"models": []}
                return R1()
            else:
                # Cancellation probe fails (daemon probe timeout / 503)
                class R2:
                    status_code = 503
                    def json(self):
                        return {}
                return R2()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    ollama_module = __import__("ragger_engine.models.ollama_manager", fromlist=["httpx"])
    ollama_module.httpx.AsyncClient = MockClient

    await manager.pull_model(spec)
    await asyncio.sleep(0.02)

    res = await manager.cancel_pull(spec.model_key)

    assert res["status"] == "failed"
    assert manager._current_progress.state == DownloadState.FAILED
    assert manager._current_progress.error_message == "Cancellation could not be confirmed by daemon"

