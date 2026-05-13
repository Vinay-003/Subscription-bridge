from __future__ import annotations

import logging
import os
import sys
from typing import Any, cast

import structlog

from subscription_bridge.utils.config import load_config

_LOG_LEVEL_ENV = "BRIDGE_LOG_LEVEL"
_LOG_FORMAT_ENV = "BRIDGE_LOG_FORMAT"
_DEFAULT_LEVEL = "INFO"
_DEFAULT_FORMAT = "console"


def _get_log_level() -> str:
    env_level = os.environ.get(_LOG_LEVEL_ENV)
    if env_level:
        return env_level.upper()

    config = load_config()
    try:
        logging_config = cast(dict[str, Any], config.get("logging", {}))
        return cast(str, logging_config.get("level", _DEFAULT_LEVEL))
    except Exception:
        return _DEFAULT_LEVEL


def _get_log_format() -> str:
    env_fmt = os.environ.get(_LOG_FORMAT_ENV)
    if env_fmt:
        return env_fmt.lower()

    config = load_config()
    try:
        logging_config = cast(dict[str, Any], config.get("logging", {}))
        return cast(str, logging_config.get("format", _DEFAULT_FORMAT))
    except Exception:
        return _DEFAULT_FORMAT


def setup_logging(level: str | None = None, fmt: str | None = None) -> None:
    level = (level or _get_log_level()).upper()
    fmt = fmt or _get_log_format()

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            (
                structlog.processors.JSONRenderer()
                if fmt == "json"
                else structlog.dev.ConsoleRenderer()
            ),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level, logging.INFO),
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name or __name__)  # type: ignore[no-any-return]


class StructuredLogger:
    def __init__(self, name: str | None = None) -> None:
        self._logger = get_logger(name)

    def debug(self, event: str, **kwargs: Any) -> None:
        self._logger.debug(event, **kwargs)

    def info(self, event: str, **kwargs: Any) -> None:
        self._logger.info(event, **kwargs)

    def warning(self, event: str, **kwargs: Any) -> None:
        self._logger.warning(event, **kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        self._logger.error(event, **kwargs)

    def critical(self, event: str, **kwargs: Any) -> None:
        self._logger.critical(event, **kwargs)

    def bind(self, **kwargs: Any) -> StructuredLogger:
        self._logger = self._logger.bind(**kwargs)
        return self
