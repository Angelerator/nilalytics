"""Automatic error submission for Python apps/services.

Call ``install()`` once at startup. After that, uncaught exceptions (main
thread and worker threads) and ``logger.exception()`` / ``logging.error(...,
exc_info=True)`` calls are sent to nilalytics as OTLP error logs
(severity ERROR + ``exception.*`` attributes) — the same shape Grafana Faro
and Sentry use. No per-error code needed.

Usage:
    from nilalytics import autocapture
    autocapture.install("my-service")
    ...                       # any uncaught error now self-reports

You can also report a handled error explicitly:
    try:
        risky()
    except Exception as exc:
        autocapture.report(exc, order_id=123)
"""

from __future__ import annotations

import logging
import sys
import threading
import time
import traceback

import requests

from . import config

_service = "nilalytics-app"


def _attr(key: str, value: str) -> dict:
    return {"key": key, "value": {"stringValue": str(value)}}


def _error_record(exc_type, exc_value, exc_tb, extra: dict | None = None) -> dict:
    stack = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    attrs = [
        _attr("event.name", "exception"),
        _attr("exception.type", getattr(exc_type, "__name__", str(exc_type))),
        _attr("exception.message", str(exc_value)),
        _attr("exception.stacktrace", stack),
    ]
    attrs += [_attr(k, v) for k, v in (extra or {}).items()]
    return {
        "timeUnixNano": str(time.time_ns()),
        "severityNumber": 17,  # ERROR
        "severityText": "ERROR",
        "body": {"stringValue": "exception"},
        "attributes": attrs,
    }


def _post(record: dict) -> None:
    payload = {
        "resourceLogs": [
            {
                "resource": {"attributes": [_attr("service.name", _service)]},
                "scopeLogs": [{"scope": {"name": "nilalytics.autocapture"},
                               "logRecords": [record]}],
            }
        ]
    }
    try:
        requests.post(
            f"{config.OTLP_HTTP}/v1/logs",
            json=payload,
            headers={"Authorization": f"Bearer {config.OTLP_TOKEN}"},
            timeout=5,
        )
    except Exception:
        # Telemetry must never crash the app it is observing.
        pass


def report(exc: BaseException, **extra) -> None:
    """Submit a handled exception explicitly."""
    _post(_error_record(type(exc), exc, exc.__traceback__, extra))


class _LoggingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if record.exc_info:
            exc_type, exc_value, exc_tb = record.exc_info
            _post(_error_record(exc_type, exc_value, exc_tb,
                                {"logger": record.name, "log.message": record.getMessage()}))


def install(service_name: str = "nilalytics-app") -> None:
    """Install global handlers so all uncaught errors self-report."""
    global _service
    _service = service_name

    # 1) uncaught exceptions on the main thread
    _prev_hook = sys.excepthook

    def _excepthook(exc_type, exc_value, exc_tb):
        _post(_error_record(exc_type, exc_value, exc_tb))
        _prev_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook

    # 2) uncaught exceptions on worker threads
    def _threadhook(args):
        _post(_error_record(args.exc_type, args.exc_value, args.exc_traceback))

    threading.excepthook = _threadhook

    # 3) logger.exception() / logging.error(..., exc_info=True)
    logging.getLogger().addHandler(_LoggingHandler())
