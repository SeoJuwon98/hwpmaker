from __future__ import annotations

import hashlib
import json
import logging
import logging.config
import sys
import traceback
from typing import Any

API_NAME = "api.hwpmaker"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_record: dict[str, Any] = {
            "level": record.levelname,
            "timestamp": self.formatTime(record, self.datefmt),
            "message": record.getMessage(),
        }
        if record.name.startswith("api") and hasattr(record, "props"):
            log_record.update(record.props)
        return json.dumps(log_record, ensure_ascii=False)


LOGGING_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "json": {
            "()": JsonFormatter,
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "formatter": "json",
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "level": "INFO",
        },
    },
    "loggers": {
        "uvicorn": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        "uvicorn.access": {"handlers": [], "level": "CRITICAL", "propagate": False},
        "fastapi": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "api": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}


def setup_logging() -> None:
    logging.config.dictConfig(LOGGING_CONFIG)


def format_exception_struct(e: Exception, max_frames: int = 30) -> dict[str, Any]:
    tb = e.__traceback__
    frames = [
        {"file": f.filename, "line": f.lineno, "func": f.name, "code": f.line}
        for f in traceback.extract_tb(tb)[-max_frames:]
    ]
    e_type = type(e)
    return {
        "type": f"{e_type.__module__}.{e_type.__name__}",
        "message": str(e),
        "frames": frames,
    }


def exception_group_key(error_type: str, frames: list[dict[str, Any]]) -> str:
    tail = frames[-3:] if frames else []
    sig = {"type": error_type, "tail": [(x["file"], x["line"], x["func"]) for x in tail]}
    raw = repr(sig).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:12]


class ApiLogger:
    def __init__(self, name: str = API_NAME) -> None:
        self._logger = logging.getLogger(name)

    def info(self, message: str, **kwargs: Any) -> None:
        self._logger.info(message, extra={"props": kwargs})

    def warning(self, message: str, **kwargs: Any) -> None:
        self._logger.warning(message, extra={"props": kwargs})

    def error(self, message: str, **kwargs: Any) -> None:
        self._logger.error(message, extra={"props": kwargs})

    def debug(self, message: str, **kwargs: Any) -> None:
        self._logger.debug(message, extra={"props": kwargs})

    def error_with_exception(self, message: str, e: Exception, **kwargs: Any) -> None:
        ex = format_exception_struct(e)
        group = exception_group_key(ex["type"], ex["frames"])
        summary = ex["frames"][-3:] if ex["frames"] else []
        props = {
            **kwargs,
            "detail": summary,
            "error_type": ex["type"],
            "error_message": ex["message"],
            "error_group": group,
            "error_frames": ex["frames"],
        }
        if props.get("status_code") is None:
            props["status_code"] = 500
        self._logger.error(message, extra={"props": props})


def get_logger(name: str = API_NAME) -> ApiLogger:
    if not name.startswith("api"):
        name = f"api.{name}"
    return ApiLogger(name)
