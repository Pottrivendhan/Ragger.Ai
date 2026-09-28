"""Structured logging setup for Ragger Engine."""

import logging
import sys
from ragger_engine.core.config import settings


class SensitiveDataFilter(logging.Filter):
    """Filter out sensitive secrets or tokens from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        token = settings.ragger_api_token
        if token and token in message:
            record.msg = message.replace(token, "[REDACTED_TOKEN]")
            record.args = ()
        return True


def setup_logging():
    """Configure structured logging for stdout and persistent logs directory."""
    import os
    from pathlib import Path

    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [ragger-engine] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    sensitive_filter = SensitiveDataFilter()

    # Stdout handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    stdout_handler.addFilter(sensitive_filter)

    handlers: list[logging.Handler] = [stdout_handler]

    # Persistent file logger in %LOCALAPPDATA%\RaggerAI\logs\engine.log
    try:
        if os.name == "nt":
            base = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
            log_dir = Path(base) / "RaggerAI" / "logs"
        else:
            log_dir = Path.home() / ".ragger_ai" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_dir / "engine.log"), encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.addFilter(sensitive_filter)
        handlers.append(file_handler)
    except Exception as e:
        # Non-fatal if log folder cannot be opened
        print(f"[Logging] Notice: Could not initialize engine.log file handler: {e}", file=sys.stderr)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()
    for h in handlers:
        root_logger.addHandler(h)

    # Uvicorn loggers
    for uvicorn_logger in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        log = logging.getLogger(uvicorn_logger)
        log.handlers.clear()
        for h in handlers:
            log.addHandler(h)
