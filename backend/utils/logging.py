"""Structured logging for SatQuery AI."""
import logging
import sys
from datetime import datetime, timezone


def setup_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("satquery")
    if logger.handlers:
        return logger
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


logger = setup_logging()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
