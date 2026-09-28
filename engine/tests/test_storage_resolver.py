"""
Tests for canonical storage root resolution contract.
Verifies:
1. Development root resolves to <repo_root>/storage.
2. Packaged root resolves to %LOCALAPPDATA%/RaggerAI/storage.
3. Development root != Packaged root.
4. RAGGER_STORAGE_DIR environment override takes top precedence.
"""

import os
import sys
from pathlib import Path
from ragger_engine.core.storage import get_storage_root, is_packaged_mode


def test_development_storage_root(monkeypatch):
    """In development mode, storage resolves to repo_root / 'storage'."""
    monkeypatch.delenv("RAGGER_STORAGE_DIR", raising=False)
    monkeypatch.delenv("RAGGER_MODE", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    storage = get_storage_root()
    repo_root = Path(__file__).resolve().parent.parent.parent
    expected = repo_root / "storage"

    assert storage == expected
    assert storage.exists()


def test_packaged_storage_root(monkeypatch, tmp_path):
    """In packaged mode, storage resolves to %LOCALAPPDATA%/RaggerAI/storage."""
    monkeypatch.delenv("RAGGER_STORAGE_DIR", raising=False)
    monkeypatch.setenv("RAGGER_MODE", "packaged")
    fake_localappdata = str(tmp_path / "fake_localappdata")
    monkeypatch.setenv("LOCALAPPDATA", fake_localappdata)

    assert is_packaged_mode() is True

    storage = get_storage_root()
    expected = Path(fake_localappdata) / "RaggerAI" / "storage"

    assert storage == expected
    assert storage.exists()


def test_development_root_not_equal_to_packaged_root(monkeypatch, tmp_path):
    """Proves: development root != packaged root."""
    monkeypatch.delenv("RAGGER_STORAGE_DIR", raising=False)
    fake_localappdata = str(tmp_path / "fake_localappdata")
    monkeypatch.setenv("LOCALAPPDATA", fake_localappdata)

    # 1. Dev root
    monkeypatch.setenv("RAGGER_MODE", "development")
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    dev_root = get_storage_root()

    # 2. Packaged root
    monkeypatch.setenv("RAGGER_MODE", "packaged")
    pkg_root = get_storage_root()

    assert dev_root != pkg_root
    assert "fake_localappdata" not in str(dev_root)
    assert "fake_localappdata" in str(pkg_root)


def test_storage_dir_env_override(monkeypatch, tmp_path):
    """RAGGER_STORAGE_DIR takes top priority over everything else."""
    override_dir = tmp_path / "custom_test_storage"
    monkeypatch.setenv("RAGGER_STORAGE_DIR", str(override_dir))
    monkeypatch.setenv("RAGGER_MODE", "packaged")
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    storage = get_storage_root()
    assert storage == override_dir.resolve()
    assert storage.exists()
