"""
Structured Logging Configuration

Provides consistent logging across the application with support for:
- Console output (development)
- JSON format (production)
- File output (optional)
- Request correlation IDs
"""

import logging
import sys
import json
from datetime import datetime, timezone
from typing import Optional, Any
from contextvars import ContextVar
from functools import lru_cache


# Context variable for request correlation
correlation_id: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


class JsonFormatter(logging.Formatter):
    """JSON formatter for production logging"""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add correlation ID if available
        corr_id = correlation_id.get()
        if corr_id:
            log_data["correlation_id"] = corr_id

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields from record
        for key, value in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "exc_info", "exc_text", "thread", "threadName",
                "taskName", "message"
            ):
                try:
                    json.dumps(value)  # Check if serializable
                    log_data[key] = value
                except (TypeError, ValueError):
                    log_data[key] = str(value)

        return json.dumps(log_data)


class ColoredFormatter(logging.Formatter):
    """Colored formatter for development console output"""

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        # Add color to level name
        color = self.COLORS.get(record.levelname, "")
        record.levelname = f"{color}{record.levelname:8}{self.RESET}"

        # Add correlation ID if available
        corr_id = correlation_id.get()
        if corr_id:
            record.msg = f"[{corr_id[:8]}] {record.msg}"

        return super().format(record)


class ContextualAdapter(logging.LoggerAdapter):
    """Logger adapter that adds contextual information"""

    def process(self, msg: str, kwargs: dict) -> tuple[str, dict]:
        extra = kwargs.get("extra", {})

        # Add correlation ID
        corr_id = correlation_id.get()
        if corr_id:
            extra["correlation_id"] = corr_id

        kwargs["extra"] = extra
        return msg, kwargs


_logging_initialized = False


def setup_logging(
    level: str = "INFO",
    json_format: bool = False,
    log_file: Optional[str] = None,
    force: bool = False
) -> None:
    """
    Configure application logging.

    Should be called once at application startup.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Use JSON format (for production)
        log_file: Optional file path for logging
        force: Force reconfiguration even if already initialized
    """
    global _logging_initialized

    if _logging_initialized and not force:
        return

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)

    if json_format:
        console_handler.setFormatter(JsonFormatter())
    else:
        console_handler.setFormatter(ColoredFormatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%H:%M:%S"
        ))

    root_logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(JsonFormatter())  # Always JSON for files
            root_logger.addHandler(file_handler)
        except (OSError, IOError) as e:
            root_logger.warning(f"Could not create log file {log_file}: {e}")

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    _logging_initialized = True

    root_logger.debug(f"Logging initialized: level={level}, json={json_format}")


def get_logger(name: str) -> ContextualAdapter:
    """
    Get a contextual logger for a module.

    Usage:
        logger = get_logger(__name__)
        logger.info("Processing request", extra={"player_id": "123"})
    """
    return ContextualAdapter(logging.getLogger(name), {})


def set_correlation_id(corr_id: str) -> None:
    """Set the correlation ID for the current context"""
    correlation_id.set(corr_id)


def get_correlation_id() -> Optional[str]:
    """Get the current correlation ID"""
    return correlation_id.get()


def generate_correlation_id() -> str:
    """Generate a new correlation ID"""
    import uuid
    corr_id = str(uuid.uuid4())
    set_correlation_id(corr_id)
    return corr_id


class LogContext:
    """Context manager for temporary logging context"""

    def __init__(self, **kwargs: Any):
        self.extra = kwargs
        self.previous_corr_id: Optional[str] = None

    def __enter__(self) -> "LogContext":
        if "correlation_id" in self.extra:
            self.previous_corr_id = get_correlation_id()
            set_correlation_id(self.extra["correlation_id"])
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.previous_corr_id is not None:
            set_correlation_id(self.previous_corr_id)
