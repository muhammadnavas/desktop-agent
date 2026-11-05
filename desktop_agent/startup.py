"""Hidden, log-file-backed entry point for the Windows logon task."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn


def configure_logging() -> Path:
    log_dir = Path(os.getenv("LOCALAPPDATA", Path.home())) / "DesktopAgent" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "agent.log"
    handler = RotatingFileHandler(
        log_file, maxBytes=2_000_000, backupCount=4, encoding="utf-8"
    )
    logging.basicConfig(
        level=os.getenv("DESKTOP_AGENT_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[handler],
        force=True,
    )
    return log_file


def main() -> None:
    log_file = configure_logging()
    logging.getLogger(__name__).info("Starting Desktop Agent background service")
    try:
        uvicorn.run(
            "desktop_agent.api:app",
            host="127.0.0.1",
            port=int(os.getenv("DESKTOP_AGENT_PORT", "8765")),
            log_config=None,
            access_log=False,
        )
    except Exception:
        logging.getLogger(__name__).exception(
            "Desktop Agent background service stopped; see %s", log_file
        )
        raise


if __name__ == "__main__":
    main()
