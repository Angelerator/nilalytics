"""nilalytics emitter: sends OTLP/HTTP log records to the ingest endpoint.

This mimics what a Grafana Faro / OpenTelemetry browser SDK emits: product
events and errors are both OTLP *log records*. Product events carry an
``event.name`` attribute; errors use severity ``ERROR`` plus ``exception.*``
attributes. The server (duckdb-otlp) lands them in the DuckLake ``otlp_logs``
table.

Run it:  uv run python -m nilalytics.emitter --count 200
"""

from __future__ import annotations

import argparse
import hashlib
import os
import random
import time
import uuid

import requests

from . import config

PRODUCT_EVENTS = ["page_view", "signup_start", "signup_complete", "add_to_cart", "purchase"]
PAGES = ["/", "/pricing", "/product", "/checkout", "/docs"]
ENV = os.getenv("NILA_ENV", "production")
HEADERS = {"Authorization": f"Bearer {config.OTLP_TOKEN}"}

# A pool of "devices" (each an anonymous.id) that normal traffic comes from.
DEVICE_POOL = [uuid.uuid4().hex for _ in range(30)]
_SESSIONS: dict[str, str] = {}


def new_anonymous_id() -> str:
    return uuid.uuid4().hex


def session_for(device: str) -> str:
    # Occasionally roll a new session for the same device.
    if device not in _SESSIONS or random.random() < 0.1:
        _SESSIONS[device] = uuid.uuid4().hex[:16]
    return _SESSIONS[device]


def hash_key(raw_key: str) -> str:
    """Pseudonymous person-key: a salted hash, done client-side. Never send raw."""
    return hashlib.sha256((config.ID_SALT + raw_key).encode()).hexdigest()[:32]


def _resource() -> dict:
    # deployment.environment is promoted to a first-class column at ingest.
    return {"attributes": [_attr("service.name", "nilalytics-web"),
                           _attr("deployment.environment", ENV)]}


def _attr(key: str, value: str) -> dict:
    return {"key": key, "value": {"stringValue": str(value)}}


def _record(event_name: str, anon: str, session: str, severity_text: str,
            severity_number: int, user: str | None = None, extra: dict | None = None) -> dict:
    # anonymous.id identifies a device; user.id (hashed) is set only once known.
    attrs = [_attr("event.name", event_name), _attr("anonymous.id", anon), _attr("session.id", session)]
    if user:
        attrs.append(_attr("user.id", user))
    attrs += [_attr(k, v) for k, v in (extra or {}).items()]
    return {
        "timeUnixNano": str(time.time_ns()),
        "severityNumber": severity_number,
        "severityText": severity_text,
        "body": {"stringValue": event_name},
        "attributes": attrs,
    }


def _payload(records: list[dict]) -> dict:
    return {
        "resourceLogs": [
            {
                "resource": _resource(),
                "scopeLogs": [
                    {
                        "scope": {"name": "nilalytics.browser"},
                        "logRecords": records,
                    }
                ],
            }
        ]
    }


def make_events(n: int, error_rate: float) -> list[dict]:
    records = []
    for _ in range(n):
        device = random.choice(DEVICE_POOL)
        session = session_for(device)
        if random.random() < error_rate:
            records.append(
                _record(
                    "exception", device, session, "ERROR", 17,
                    extra={
                        "exception.type": random.choice(["TypeError", "NetworkError", "RangeError"]),
                        "exception.message": "Cannot read properties of undefined",
                        "page": random.choice(PAGES),
                    },
                )
            )
        else:
            records.append(
                _record(
                    random.choice(PRODUCT_EVENTS), device, session, "INFO", 9,
                    extra={"page": random.choice(PAGES)},
                )
            )
    return records


def emit(count: int, batch_size: int, error_rate: float) -> int:
    url = f"{config.OTLP_HTTP}/v1/logs"
    sent = 0
    while sent < count:
        this = min(batch_size, count - sent)
        resp = requests.post(url, json=_payload(make_events(this, error_rate)),
                             headers=HEADERS, timeout=10)
        resp.raise_for_status()
        sent += this
        print(f"POST {this:>4} logs -> {resp.status_code} {resp.json()}", flush=True)
    print(f"[emitter] sent {sent} log events to {url}", flush=True)
    return sent


def _post_logs(records: list[dict]) -> None:
    resp = requests.post(f"{config.OTLP_HTTP}/v1/logs", json=_payload(records), headers=HEADERS, timeout=10)
    resp.raise_for_status()


def identify(device: str, user_key: str) -> str:
    """Link a device's anonymous.id to a hashed person-key (an 'identify' event)."""
    uid = hash_key(user_key)
    _post_logs([_record("identify", device, session_for(device), "INFO", 9, user=uid, extra={"method": "login"})])
    return uid


def emit_cross_device(persons: int, events_per_device: int = 8) -> None:
    """Simulate each person using two devices, then logging in on both.

    Before login the two devices are unlinkable; the identify events tie both
    anonymous.ids to the same hashed person-key, enabling cross-device stitching.
    """
    for i in range(persons):
        user_key = f"person{i}@example.com"
        uid = hash_key(user_key)
        for _ in range(2):  # phone + laptop
            device = new_anonymous_id()
            session = uuid.uuid4().hex[:16]
            # anonymous activity first
            _post_logs([_record(random.choice(PRODUCT_EVENTS), device, session, "INFO", 9,
                                extra={"page": random.choice(PAGES)}) for _ in range(events_per_device)])
            # then the user logs in on this device
            identify(device, user_key)
        print(f"[emitter] person{i}: 2 devices -> {uid[:12]}...", flush=True)
    print(f"[emitter] cross-device sim: {persons} persons x 2 devices", flush=True)


# --- Traces (performance spans, e.g. page loads / API calls) ---
def make_spans(n: int) -> list[dict]:
    spans = []
    for _ in range(n):
        start = time.time_ns()
        duration_ns = random.randint(20, 800) * 1_000_000  # 20-800 ms
        spans.append({
            "traceId": os.urandom(16).hex(),
            "spanId": os.urandom(8).hex(),
            "name": random.choice(["page_load", "api_call", "route_change"]),
            "kind": 1,
            "startTimeUnixNano": str(start),
            "endTimeUnixNano": str(start + duration_ns),
            "attributes": [_attr("page", random.choice(PAGES))],
        })
    return spans


def emit_traces(n: int) -> None:
    payload = {"resourceSpans": [{"resource": _resource(),
                                  "scopeSpans": [{"scope": {"name": "nilalytics.browser"},
                                                  "spans": make_spans(n)}]}]}
    resp = requests.post(f"{config.OTLP_HTTP}/v1/traces", json=payload, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    print(f"[emitter] sent {n} spans -> {resp.status_code}", flush=True)


# --- AI usage (LLM calls: model + token usage; subject 'ai_usage') ---
AI_PROVIDERS = [("openai", "gpt-4o"), ("anthropic", "claude-3-5-sonnet"), ("google", "gemini-1.5-pro")]


def make_ai_events(n: int) -> list[dict]:
    records = []
    for _ in range(n):
        device = random.choice(DEVICE_POOL)
        system, model = random.choice(AI_PROVIDERS)
        records.append(
            _record(
                "ai_request", device, session_for(device), "INFO", 9,
                extra={
                    "gen_ai.system": system,
                    "gen_ai.request.model": model,
                    "gen_ai.usage.input_tokens": str(random.randint(50, 2000)),
                    "gen_ai.usage.output_tokens": str(random.randint(20, 1500)),
                },
            )
        )
    return records


def emit_ai(n: int) -> None:
    _post_logs(make_ai_events(n))
    print(f"[emitter] sent {n} ai_usage events", flush=True)


# --- Metrics (e.g. web-vitals gauges) ---
def make_points(n: int) -> list[dict]:
    return [{"timeUnixNano": str(time.time_ns()),
             "asDouble": round(random.uniform(200, 4000), 1),
             "attributes": [_attr("page", random.choice(PAGES))]} for _ in range(n)]


def emit_metrics(n: int) -> None:
    payload = {"resourceMetrics": [{"resource": _resource(),
                                    "scopeMetrics": [{"scope": {"name": "nilalytics.browser"},
                                                      "metrics": [{"name": "web_vitals_lcp_ms",
                                                                   "unit": "ms",
                                                                   "gauge": {"dataPoints": make_points(n)}}]}]}]}
    resp = requests.post(f"{config.OTLP_HTTP}/v1/metrics", json=payload, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    print(f"[emitter] sent {n} metric points -> {resp.status_code}", flush=True)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="nilalytics emit",
                                     description="Emit OTLP logs, traces and metrics to nilalytics.")
    parser.add_argument("-n", "--count", type=int, default=200, help="log events")
    parser.add_argument("-b", "--batch-size", type=int, default=50)
    parser.add_argument("-e", "--error-rate", type=float, default=0.1)
    parser.add_argument("--traces", type=int, default=10, help="trace spans")
    parser.add_argument("--metrics", type=int, default=10, help="metric points")
    parser.add_argument("--ai", type=int, default=5, help="ai_usage events (LLM calls)")
    parser.add_argument("--persons", type=int, default=0,
                        help="simulate N cross-device persons (2 devices each, identified)")
    args = parser.parse_args(argv)
    if args.count:
        emit(args.count, args.batch_size, args.error_rate)
    if args.traces:
        emit_traces(args.traces)
    if args.metrics:
        emit_metrics(args.metrics)
    if args.ai:
        emit_ai(args.ai)
    if args.persons:
        emit_cross_device(args.persons)


if __name__ == "__main__":
    main()
