"""Hidden, log-file-backed entry point for the Windows logon task."""

from __future__ import annotations

import logging
import os

import uvicorn

from desktop_agent.logging_config import configure_logging


def main() -> None:
    log_file = configure_logging()
    logging.getLogger(__name__).info("Starting Desktop Agent background service | activity_log=%s", log_file)
    try:
        uvicorn.run(
            "desktop_agent.api:app",
            host="127.0.0.1",
            port=int(os.getenv("DESKTOP_AGENT_PORT", "8765")),
            log_config=None,
            access_log=False,
        )
    except Exception:
        logging.getLogger(__name__).exception("Desktop Agent background service stopped; see %s", log_file)
        raise


if __name__ == "__main__":
    main()
