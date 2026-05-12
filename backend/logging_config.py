"""Centralised logging configuration for Shield AI.

Call ``setup_logging()`` once at application startup (in main.py before any
other imports that use logging).  Every module that calls
``logging.getLogger(__name__)`` will then inherit this configuration
automatically.

Log layout
----------
logs/
  shield_2026-05-12.log   ← today
  shield_2026-05-11.log   ← yesterday (rolled at midnight)
  …up to LOG_RETENTION_DAYS files

Each line:
  2026-05-12 14:23:01,482 [INFO ] backend.api.contracts upload — Contract 7 queued
  2026-05-12 14:23:01,823 [ERROR] backend.agents.risk run — Agent 'risk' failed
  Traceback (most recent call last):
    ...

Two handlers are always active:
  • TimedRotatingFileHandler — rotates at midnight UTC, keeps LOG_RETENTION_DAYS files
  • StreamHandler (stdout)   — for Cloud Run / Docker log capture
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path

# ------------------------------------------------------------------
# Configuration — override via environment variables if needed
# ------------------------------------------------------------------
LOG_DIR = Path(os.getenv("SHIELD_LOG_DIR", "logs"))
LOG_RETENTION_DAYS = int(os.getenv("SHIELD_LOG_RETENTION_DAYS", "30"))
LOG_LEVEL = os.getenv("SHIELD_LOG_LEVEL", "INFO").upper()

# Log format — includes timestamp, level (fixed width), logger name, and message
_FMT = "%(asctime)s [%(levelname)-5s] %(name)s %(funcName)s — %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"

_configured = False  # guard against calling setup_logging() more than once


def setup_logging() -> None:
    """Configure root logger with daily rotating file + stdout handlers.

    Safe to call multiple times — only the first call has any effect.
    """
    global _configured
    if _configured:
        return
    _configured = True

    # Create logs/ directory if it doesn't exist
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    formatter = logging.Formatter(fmt=_FMT, datefmt=_DATE_FMT)

    # ---- File handler — rotates at midnight, filename suffix = date ----
    log_file = LOG_DIR / "shield.log"
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",       # rotate at midnight UTC
        interval=1,            # every 1 day
        backupCount=LOG_RETENTION_DAYS,
        encoding="utf-8",
        utc=True,              # use UTC for rotation timing
    )
    # Suffix makes rolled files look like: shield.log.2026-05-11
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setFormatter(formatter)

    # ---- Console handler — stdout for Cloud Run / Docker ----
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # Remove any handlers already attached (e.g. from a prior basicConfig call)
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # Quiet down noisy third-party libraries
    for noisy in ("uvicorn.access", "httpx", "google.auth", "urllib3", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    root.info(
        "Logging initialised — level=%s  file=%s  retention=%d days",
        LOG_LEVEL, log_file.resolve(), LOG_RETENTION_DAYS,
    )
