"""Shared rotating file logging for the Desktop Agent."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging() -> Path:
    """Configure a rotating local log without duplicate file handlers."""
    log_dir = Path(os.getenv("LOCALAPPDATA", Path.home())) / "DesktopAgent" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "agent.log"
    root = logging.getLogger()
    root.setLevel(os.getenv("DESKTOP_AGENT_LOG_LEVEL", "INFO").upper())
    if not any(isinstance(h, RotatingFileHandler) and Path(h.baseFilename).resolve() == log_file.resolve() for h in root.handlers):
        handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=4, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(handler)
    return log_file
