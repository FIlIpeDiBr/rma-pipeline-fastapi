"""Logs estruturados (JSON em produção, legível em dev) com correlation id."""

import logging

import structlog

from .config import get_settings


def setup_logging() -> None:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    renderer: structlog.types.Processor
    if settings.is_production:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )
