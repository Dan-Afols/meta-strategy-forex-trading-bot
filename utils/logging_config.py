"""
Structured logging configuration using structlog.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import structlog


_logging_configured = False


def setup_logging(log_level: str = "INFO", log_dir: str = "./logs") -> None:
    """Configure structured logging for the entire application."""
    global _logging_configured
    if _logging_configured:
        return
    _logging_configured = True

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # File handler
    file_handler = logging.FileHandler(log_path / "trading.log", encoding="utf-8")
    file_handler.setLevel(getattr(logging, log_level))

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level))

    # Configure root logger
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level),
        handlers=[file_handler, console_handler],
    )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a named structured logger."""
    return structlog.get_logger(name)
