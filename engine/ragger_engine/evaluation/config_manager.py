"""
Configuration manager for Phase 8 Automated Quality Evaluation & Benchmarking Subsystem.
Persists and loads evaluation_config.json atomically with strict extra='forbid' validation.
"""

import json
import os
from pathlib import Path

from .models import EvaluationConfig


def get_evaluation_config(workspace_dir: Path) -> EvaluationConfig:
    """Reads evaluation configuration from workspace directory or returns strict defaults."""
    cfg_file = workspace_dir / "evaluation_config.json"
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return EvaluationConfig.model_validate(data)
        except Exception:
            pass
    return EvaluationConfig()


def save_evaluation_config(workspace_dir: Path, config: EvaluationConfig) -> EvaluationConfig:
    """Atomically persists evaluation configuration to workspace directory."""
    cfg_file = workspace_dir / "evaluation_config.json"
    tmp_file = workspace_dir / "evaluation_config.json.tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        f.write(config.model_dump_json(indent=2))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_file, cfg_file)
    return config
