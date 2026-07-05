"""Central configuration for nilalytics.

Every value can be overridden with an environment variable so the same code runs
against local MinIO now and Cloudflare R2 later (R2 is S3-compatible).
"""

from __future__ import annotations

import json
import os
import secrets
import stat
from pathlib import Path

# Writable data directory (catalog file + secrets). Deliberately NOT relative to
# the package install location, so nilalytics works from any working directory
# and when pip-installed. Override with NILA_DATA_DIR.
DATA_DIR = Path(os.getenv("NILA_DATA_DIR", Path.home() / ".nilalytics")).expanduser()
DATA_DIR.mkdir(parents=True, exist_ok=True)

# --- Secrets: never hardcode. Load from env, else generate once and persist
# to a 0600 file under data/ (which is git-ignored). token_urlsafe() is safe in
# both HTTP headers and single-quoted SQL strings. ---
_SECRETS_FILE = DATA_DIR / ".nila_secrets.json"


def _load_or_create_secrets() -> dict:
    data = {}
    if _SECRETS_FILE.exists():
        try:
            data = json.loads(_SECRETS_FILE.read_text())
        except (ValueError, OSError):
            data = {}
    changed = False
    for key in ("otlp_token", "quack_token", "id_salt", "gateway_secret", "ingest_key"):
        if not data.get(key):
            data[key] = secrets.token_urlsafe(24)
            changed = True
    if changed:
        _SECRETS_FILE.write_text(json.dumps(data))
        try:
            _SECRETS_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600, owner-only
        except OSError:
            pass
    return data


_SECRETS = _load_or_create_secrets()

# --- Object storage backend (works on all major clouds) ---
# NILA_STORAGE selects the cloud: s3 | gcs | r2 | azure. See storage.py.
STORAGE = os.getenv("NILA_STORAGE", "s3").lower()
# Bucket (or Azure *container*) + key prefix, shared across backends.
BUCKET = os.getenv("NILA_BUCKET", os.getenv("NILA_S3_BUCKET", "nilalytics"))
PREFIX = os.getenv("NILA_PREFIX", "lake")

# S3 / MinIO / any S3-compatible store. Leave endpoint empty for real AWS S3.
S3_ENDPOINT = os.getenv("NILA_S3_ENDPOINT", "127.0.0.1:9100")
S3_ACCESS_KEY = os.getenv("NILA_S3_KEY", "minioadmin")
S3_SECRET_KEY = os.getenv("NILA_S3_SECRET", "minioadmin")
S3_SESSION_TOKEN = os.getenv("NILA_S3_SESSION_TOKEN", "")  # optional STS token
S3_USE_SSL = os.getenv("NILA_S3_USE_SSL", "false").lower() == "true"
S3_URL_STYLE = os.getenv("NILA_S3_URL_STYLE", "path")  # MinIO/R2 want path style
S3_REGION = os.getenv("NILA_S3_REGION", "us-east-1")

# Google Cloud Storage (HMAC interoperability keys).
GCS_KEY = os.getenv("NILA_GCS_KEY", "")
GCS_SECRET = os.getenv("NILA_GCS_SECRET", "")

# Cloudflare R2.
R2_ACCOUNT_ID = os.getenv("NILA_R2_ACCOUNT_ID", "")
R2_KEY = os.getenv("NILA_R2_KEY", "")
R2_SECRET = os.getenv("NILA_R2_SECRET", "")

# Azure Blob / ADLS Gen2 (BUCKET is the container).
AZURE_ACCOUNT = os.getenv("NILA_AZURE_ACCOUNT", "")
AZURE_AUTH = os.getenv("NILA_AZURE_AUTH", "credential_chain")  # credential_chain|connection_string|service_principal
AZURE_CONNECTION_STRING = os.getenv("NILA_AZURE_CONNECTION_STRING", "")
AZURE_TENANT_ID = os.getenv("NILA_AZURE_TENANT_ID", "")
AZURE_CLIENT_ID = os.getenv("NILA_AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET = os.getenv("NILA_AZURE_CLIENT_SECRET", "")

# --- DuckLake catalog (a DuckDB file, served to clients over Quack) ---
CATALOG_PATH = os.getenv("NILA_CATALOG", str(DATA_DIR / "catalog.ducklake"))
# Inserts smaller than this land as rows inside the catalog (data inlining),
# so streaming events never create tiny Parquet files.
DATA_INLINING_ROW_LIMIT = int(os.getenv("NILA_INLINE_LIMIT", "1000"))

# --- OTLP ingest server (duckdb-otlp) ---
OTLP_URI = os.getenv("NILA_OTLP_URI", "otlp:127.0.0.1:4318")
OTLP_HTTP = os.getenv("NILA_OTLP_HTTP", "http://127.0.0.1:4318")
# Bearer token that ingest clients (emitter, autocapture, browser) must present.
# This is the INTERNAL token; it never leaves the host once the gateway is used.
OTLP_TOKEN = os.getenv("NILA_OTLP_TOKEN", _SECRETS["otlp_token"])

# --- Public ingest gateway (front door for browsers + mobile) ---
# Set host to 0.0.0.0 to accept real devices/browsers. Optional TLS via cert/key.
GATEWAY_HOST = os.getenv("NILA_GATEWAY_HOST", "127.0.0.1")
GATEWAY_PORT = int(os.getenv("NILA_GATEWAY_PORT", "4319"))
GATEWAY_CORS_ORIGINS = os.getenv("NILA_GATEWAY_CORS", "*")
GATEWAY_CERT = os.getenv("NILA_GATEWAY_CERT", "")
GATEWAY_KEY = os.getenv("NILA_GATEWAY_KEY", "")
# Short-lived client tokens are HMAC-signed with this secret and expire after TTL.
GATEWAY_SECRET = os.getenv("NILA_GATEWAY_SECRET", _SECRETS["gateway_secret"])
GATEWAY_TOKEN_TTL = int(os.getenv("NILA_GATEWAY_TOKEN_TTL", "900"))  # 15 min
# The (rotatable) key an app presents to MINT a short-lived token. This is the
# only value that ships in a client; it grants minting, not ingest or reads.
GATEWAY_INGEST_KEY = os.getenv("NILA_INGEST_KEY", _SECRETS["ingest_key"])

# --- Quack catalog server (read path for clients / DuckDB-WASM) ---
QUACK_URI = os.getenv("NILA_QUACK_URI", "quack:localhost")
QUACK_TOKEN = os.getenv("NILA_QUACK_TOKEN", _SECRETS["quack_token"])

# Name the DuckLake is attached as, inside the server process.
LAKE = "lake"

# --- Ingest tuning (package defaults; override via env) ---
# Freshness: force a commit when the oldest buffered row hits this age.
SEAL_MAX_AGE_MS = int(os.getenv("NILA_SEAL_MAX_AGE_MS", "1000"))
# Retention: how long snapshots/old files are kept before maintenance reclaims them.
MAINTENANCE_RETENTION_MS = int(os.getenv("NILA_RETENTION_MS", str(7 * 24 * 3600 * 1000)))
# Resource attributes lifted into first-class columns at ingest for pruning
# (comma-separated; empty disables). Event-level fields stay in log_attributes.
PROMOTE_RESOURCE_ATTRS = os.getenv("NILA_PROMOTE_RESOURCE_ATTRS", "deployment.environment")

# Salt for pseudonymous identity hashing. User keys (email/account id) are hashed
# with this salt client-side, so the lake stores a stable person-key it cannot
# reverse into a real identity.
ID_SALT = os.getenv("NILA_ID_SALT", _SECRETS["id_salt"])

# --- Physical layout applied to the events table (query performance) ---
# Partition transforms: identity | bucket(N,col) | year|month|day|hour(ts).
PARTITION_BY = os.getenv("NILA_PARTITION_BY", "day(time_unix_nano)")
SORTED_BY = os.getenv("NILA_SORTED_BY", "body, time_unix_nano")

# --- Curated user_events table (built for per-user reads: recommendations / ML) ---
# A downstream table that lifts identity + the common event fields out of the
# otlp_logs JSON into typed, first-class columns. It is partitioned by day (a
# low-cardinality key) and CLUSTERED (sorted) by person_id, so "give me one
# user's history" prunes to a handful of files -- WITHOUT the partition-per-user
# tiny-file explosion that keying the partition on user_id would cause.
USER_EVENTS_ENABLED = os.getenv("NILA_USER_EVENTS", "true").lower() == "true"
USER_EVENTS_TABLE = os.getenv("NILA_USER_EVENTS_TABLE", "user_events")
# The server refreshes it incrementally (DuckLake change feed) on this cadence.
USER_EVENTS_REFRESH_SECONDS = int(os.getenv("NILA_USER_EVENTS_REFRESH_SECONDS", "60"))
# Physical layout of the curated table. subject (a handful) and day() are natural
# LOW-cardinality partitions. person_id is HIGH-cardinality, so it is partitioned
# via bucket(N, ...) -- Iceberg-style hashing into N folders -- which is DuckLake's
# recommended way to partition on a high-cardinality key WITHOUT the
# millions-of-tiny-files problem. person_id is also a SORT key, so one person's
# rows are contiguous inside their bucket.
#
# The three partition levels multiply (subject x days x N buckets). Tune for volume:
#   * high volume  -> raise NILA_USER_EVENTS_BUCKETS (e.g. 256) for finer pruning;
#   * low volume   -> drop day, e.g. NILA_USER_EVENTS_PARTITION_BY="subject, bucket(256, person_id)".
# Compaction (nilalytics maintenance) merges small files WITHIN each partition.
USER_EVENTS_BUCKETS = int(os.getenv("NILA_USER_EVENTS_BUCKETS", "16"))
USER_EVENTS_PARTITION_BY = os.getenv(
    "NILA_USER_EVENTS_PARTITION_BY",
    f"subject, day(event_time), bucket({USER_EVENTS_BUCKETS}, person_id)",
)
USER_EVENTS_SORTED_BY = os.getenv("NILA_USER_EVENTS_SORTED_BY", "person_id, event_time_unix_nano")

# --- Data retention (drop events older than N days so storage stays bounded) ---
# NOTE: this is EVENT/ROW retention -- it deletes old rows from the event tables.
# It is different from NILA_RETENTION_MS above, which controls how long DuckLake
# keeps SNAPSHOTS/old files (time-travel history) before they are reclaimed.
# Deleting data is destructive, so row retention is strictly OPT-IN: 0 = disabled.
RETENTION_DAYS = int(os.getenv("NILA_RETENTION_DAYS", "0"))
# How often the server runs the retention sweep (seconds).
RETENTION_INTERVAL_SECONDS = int(os.getenv("NILA_RETENTION_INTERVAL_SECONDS", "3600"))

# --- Safety guardrails ---
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


def endpoint_host() -> str:
    return S3_ENDPOINT.split(":")[0]


def is_local_endpoint() -> bool:
    return endpoint_host() in _LOCAL_HOSTS


def assert_safe() -> None:
    """Refuse obviously-insecure configurations before starting the server."""
    # Only the S3 backend has the local-MinIO / default-cred footgun. GCS, R2 and
    # Azure are inherently remote + TLS and are validated in storage.py.
    if STORAGE != "s3" or is_local_endpoint():
        return
    problems = []
    if not S3_USE_SSL:
        problems.append("remote S3 requires TLS (set NILA_S3_USE_SSL=true)")
    if S3_ACCESS_KEY == "minioadmin" or S3_SECRET_KEY == "minioadmin":
        problems.append("default 'minioadmin' credentials must not be used with a remote endpoint")
    if problems:
        raise SystemExit("[nilalytics] refusing to start:\n  - " + "\n  - ".join(problems))
