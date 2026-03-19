"""
Logging utilities compatible with Result<T> pattern.

Provides structured logging that doesn't throw exceptions.
"""

import logging
import sys
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .result import Result, Error


def setup_logger(name: str) -> logging.Logger:
    """Setup module logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


_logger = setup_logger("omni_sdk")


def log_debug(message: str, **kwargs) -> None:
    """Log debug message."""
    if _logger.isEnabledFor(logging.DEBUG):
        _log(logging.DEBUG, message, **kwargs)


def log_info(message: str, **kwargs) -> None:
    """Log info message."""
    if _logger.isEnabledFor(logging.INFO):
        _log(logging.INFO, message, **kwargs)


def log_warning(message: str, **kwargs) -> None:
    """Log warning message."""
    if _logger.isEnabledFor(logging.WARNING):
        _log(logging.WARNING, message, **kwargs)


def log_error(message: str, err_obj: Optional["Error"] = None, **kwargs) -> None:
    """Log error message."""
    if err_obj:
        log_data = {"error_kind": err_obj.kind, "error_message": err_obj.message}
        if err_obj.details:
            log_data["error_details"] = err_obj.details
        kwargs.update(log_data)

    _log(logging.ERROR, message, **kwargs)


def log_result(result: "Result[Any]", operation: str) -> None:
    """Log result of operation."""
    if result.is_ok:
        log_info(f"{operation}: succeeded")
    else:
        err = result._error
        log_error(f"{operation}: failed ({err.kind})", err_obj=err)


def set_log_level(level: str) -> "Result[None]":
    """
    Set log level.

    Args:
        level: Log level ("debug", "info", "warning", "error", "critical")

    Returns:
        Result.ok(None) on success, Result.err on invalid level
    """
    valid_levels = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }

    level_lower = level.lower()
    if level_lower not in valid_levels:
        # Late import to avoid circular dependency
        sys.path.insert(0, sys.path[0] + "/omni_sdk")
        from result import ErrorKinds, create_error_result

        return create_error_result(
            kind=ErrorKinds.CONFIG_ERROR,
            message=f"Invalid log level: {level}",
            details={"valid_levels": list(valid_levels.keys())},
        )

    _logger.setLevel(valid_levels[level_lower])
    return Result.ok(None)


def _log(level: int, message: str, **kwargs) -> None:
    """Internal logging function."""
    if kwargs:
        message = f"{message} | {kwargs}"
    _logger.log(level, message)


__all__ = [
    "log_debug",
    "log_info",
    "log_warning",
    "log_error",
    "log_result",
    "set_log_level",
]
