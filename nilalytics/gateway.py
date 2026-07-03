"""Public ingest gateway for nilalytics.

The internal ``duckdb-otlp`` server supports only a single static token and binds
to localhost. This gateway is the public-facing front door and fixes the
client-facing caveats solidly:

  * CORS: adds Access-Control-Allow-* headers and answers preflight, so browsers
    (Grafana Faro) can post cross-origin.
  * Public bind + optional TLS: binds a configurable host/port and can terminate
    TLS directly (cert/key), or sit behind a reverse proxy. The internal OTLP
    server stays on localhost.
  * Short-lived tokens: clients never ship the internal ingest token. They fetch
    a short-lived, HMAC-signed token from ``POST /v1/token`` (authorized by a
    rotatable ingest key) and use it for a limited window. The gateway verifies
    it and forwards to the internal OTLP server with the internal token.

Run it:  uv run python -m nilalytics.gateway
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import ssl
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

from . import config

_INGEST_PATHS = {"/v1/logs", "/v1/traces", "/v1/metrics"}


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: str) -> str:
    mac = hmac.new(config.GATEWAY_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
    return _b64(mac)


def mint_token(ttl: int | None = None) -> str:
    exp = int(time.time()) + (ttl or config.GATEWAY_TOKEN_TTL)
    payload = _b64(json.dumps({"exp": exp}).encode())
    return f"{payload}.{_sign(payload)}"


def verify_token(token: str) -> bool:
    try:
        payload, sig = token.split(".", 1)
    except ValueError:
        return False
    if not hmac.compare_digest(sig, _sign(payload)):
        return False
    try:
        data = json.loads(_unb64(payload))
    except Exception:  # noqa: BLE001 - any decode failure = invalid token
        return False
    return int(data.get("exp", 0)) > int(time.time())


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", config.GATEWAY_CORS_ORIGINS)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers",
                         "Authorization, Content-Type, x-api-key, x-ingest-key")
        self.send_header("Access-Control-Max-Age", "86400")

    def _reply(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # CORS preflight
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        self._reply(200, {"status": "ok"}) if self.path == "/healthz" else self._reply(404, {"error": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b""

        if self.path == "/v1/token":
            presented = self.headers.get("x-ingest-key", "")
            if not hmac.compare_digest(presented, config.GATEWAY_INGEST_KEY):
                self._reply(401, {"error": "invalid ingest key"})
                return
            self._reply(200, {"token": mint_token(), "expires_in": config.GATEWAY_TOKEN_TTL})
            return

        if self.path in _INGEST_PATHS:
            auth = self.headers.get("Authorization", "")
            token = auth[7:].strip() if auth.lower().startswith("bearer ") else self.headers.get("x-api-key", "")
            if not verify_token(token):
                self._reply(401, {"error": "invalid or expired token"})
                return
            try:
                upstream = requests.post(
                    f"{config.OTLP_HTTP}{self.path}",
                    data=body,
                    headers={
                        "Content-Type": self.headers.get("Content-Type", "application/json"),
                        "Authorization": f"Bearer {config.OTLP_TOKEN}",
                    },
                    timeout=15,
                )
            except requests.RequestException as exc:
                self._reply(502, {"error": f"upstream unavailable: {exc}"})
                return
            try:
                payload = upstream.json()
            except ValueError:
                payload = {"status": upstream.status_code}
            self._reply(upstream.status_code, payload)
            return

        self._reply(404, {"error": "not found"})

    def log_message(self, *_args) -> None:  # keep the console quiet
        pass


def main(argv=None) -> None:  # argv accepted for CLI compatibility (unused)
    httpd = ThreadingHTTPServer((config.GATEWAY_HOST, config.GATEWAY_PORT), _Handler)
    scheme = "http"
    if config.GATEWAY_CERT and config.GATEWAY_KEY:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(config.GATEWAY_CERT, config.GATEWAY_KEY)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        scheme = "https"

    base = f"{scheme}://{config.GATEWAY_HOST}:{config.GATEWAY_PORT}"
    print(f"[nilalytics] gateway ready: {base}", flush=True)
    print(f"[nilalytics]   mint:   POST /v1/token   (header 'x-ingest-key')", flush=True)
    print(f"[nilalytics]   ingest: POST /v1/logs|/v1/traces|/v1/metrics (Bearer short-lived token)", flush=True)
    print(f"[nilalytics]   forwards to internal {config.OTLP_HTTP}", flush=True)
    print("[nilalytics] GATEWAY READY", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()
        print("[nilalytics] gateway stopped", flush=True)


if __name__ == "__main__":
    main()
