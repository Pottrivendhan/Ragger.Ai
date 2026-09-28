"""
Canonical Storage Root Resolver for Ragger.ai.
Enforces the strict storage contracts:
- Development mode: C:\\Users\\POTTRIVENDHAN\\Ragger.ai\\storage
- Packaged mode:    %LOCALAPPDATA%\\RaggerAI\\storage
- Environment test override: RAGGER_STORAGE_DIR
"""

import os
import sys
from pathlib import Path


def is_packaged_mode() -> bool:
    """Returns True if running in a frozen/packaged PyInstaller distribution or production environment."""
    return getattr(sys, "frozen", False) or os.environ.get("RAGGER_MODE") == "packaged"


def get_storage_root() -> Path:
    """
    Resolves the canonical persistent storage directory.
    Priority:
    1. Explicit environment override: RAGGER_STORAGE_DIR
    2. Packaged production: %LOCALAPPDATA%\\RaggerAI\\storage (or ~/.ragger_ai/storage)
    3. Development mode: <repository_root>\\storage
    """
    if "RAGGER_STORAGE_DIR" in os.environ:
        root = Path(os.environ["RAGGER_STORAGE_DIR"]).resolve()
    elif is_packaged_mode():
        if os.name == "nt":
            base = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
            root = Path(base) / "RaggerAI" / "storage"
        else:
            root = Path.home() / ".ragger_ai" / "storage"
    else:
        # Development mode: <repo_root>/storage
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        root = repo_root / "storage"

    root.mkdir(parents=True, exist_ok=True)
    return root
