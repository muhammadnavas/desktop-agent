"""Shared console and rotating-file logging for the Desktop Agent."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging() -> Path:
    """Configure terminal + rotating local logs without duplicate handlers."""
    log_dir = Path(os.getenv("LOCALAPPDATA", Path.home())) / "DesktopAgent" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "agent.log"
    root = logging.getLogger()
    root.setLevel(os.getenv("DESKTOP_AGENT_LOG_LEVEL", "INFO").upper())
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    if not any(getattr(handler, "_desktop_agent_console", False) for handler in root.handlers):
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        console._desktop_agent_console = True
        root.addHandler(console)

    if not any(isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename).resolve() == log_file.resolve() for handler in root.handlers):
        file_handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=4, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    return log_file
