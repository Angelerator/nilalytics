"""Pluggable object-storage backends for nilalytics.

One env var (``NILA_STORAGE``) selects the cloud; only this module knows the
cloud-specific details. ``server.py`` calls :func:`configure`, which loads the
right DuckDB extension(s), registers the credentials secret, and returns the
DuckLake ``DATA_PATH`` URI. Switching clouds is entirely env-driven.

Supported backends (all verified against DuckDB docs):
  - ``s3``    AWS S3 and any S3-compatible store (MinIO, Tigris, ...) via ENDPOINT
  - ``gcs``   Google Cloud Storage (HMAC interop keys), gs:// paths
  - ``r2``    Cloudflare R2 (ACCOUNT_ID), r2:// paths
  - ``azure`` Azure Blob / ADLS Gen2, abfss:// paths
"""

from __future__ import annotations

from . import config


def _s3_secret() -> str:
    parts = [
        f"KEY_ID '{config.S3_ACCESS_KEY}'",
        f"SECRET '{config.S3_SECRET_KEY}'",
        f"REGION '{config.S3_REGION}'",
        f"URL_STYLE '{config.S3_URL_STYLE}'",
        f"USE_SSL {str(config.S3_USE_SSL).lower()}",
    ]
    if config.S3_ENDPOINT:  # empty for real AWS S3
        parts.append(f"ENDPOINT '{config.S3_ENDPOINT}'")
    if config.S3_SESSION_TOKEN:  # short-lived STS credentials
        parts.append(f"SESSION_TOKEN '{config.S3_SESSION_TOKEN}'")
    return "CREATE OR REPLACE SECRET object_store (TYPE s3, " + ", ".join(parts) + ");"


def _gcs_secret() -> str:
    return ("CREATE OR REPLACE SECRET object_store (TYPE gcs, "
            f"KEY_ID '{config.GCS_KEY}', SECRET '{config.GCS_SECRET}');")


def _r2_secret() -> str:
    # REGION 'auto' is required since DuckDB 1.1.1.
    return ("CREATE OR REPLACE SECRET object_store (TYPE r2, "
            f"ACCOUNT_ID '{config.R2_ACCOUNT_ID}', KEY_ID '{config.R2_KEY}', "
            f"SECRET '{config.R2_SECRET}', REGION 'auto');")


def _azure_secret() -> str:
    if config.AZURE_AUTH == "connection_string":
        return ("CREATE OR REPLACE SECRET object_store (TYPE azure, "
                f"CONNECTION_STRING '{config.AZURE_CONNECTION_STRING}');")
    if config.AZURE_AUTH == "service_principal":
        return ("CREATE OR REPLACE SECRET object_store (TYPE azure, PROVIDER service_principal, "
                f"TENANT_ID '{config.AZURE_TENANT_ID}', CLIENT_ID '{config.AZURE_CLIENT_ID}', "
                f"CLIENT_SECRET '{config.AZURE_CLIENT_SECRET}', ACCOUNT_NAME '{config.AZURE_ACCOUNT}');")
    # default: credential_chain -> managed identity / az CLI / env vars
    return ("CREATE OR REPLACE SECRET object_store (TYPE azure, PROVIDER credential_chain, "
            f"ACCOUNT_NAME '{config.AZURE_ACCOUNT}');")


_BACKENDS = {
    "s3": {
        "exts": ("httpfs",),
        "secret": _s3_secret,
        "path": lambda: f"s3://{config.BUCKET}/{config.PREFIX}",
    },
    "gcs": {
        "exts": ("httpfs",),
        "secret": _gcs_secret,
        "path": lambda: f"gs://{config.BUCKET}/{config.PREFIX}",
    },
    "r2": {
        "exts": ("httpfs",),
        "secret": _r2_secret,
        "path": lambda: f"r2://{config.BUCKET}/{config.PREFIX}",
    },
    "azure": {
        "exts": ("azure",),
        "secret": _azure_secret,
        "path": lambda: (f"abfss://{config.BUCKET}@{config.AZURE_ACCOUNT}"
                         f".dfs.core.windows.net/{config.PREFIX}"),
    },
}


def data_path() -> str:
    """The DuckLake DATA_PATH URI for the selected backend."""
    return _BACKENDS[config.STORAGE]["path"]()


def _validate() -> None:
    backend = config.STORAGE
    if backend not in _BACKENDS:
        raise SystemExit(
            f"[nilalytics] unknown NILA_STORAGE '{backend}'. Use one of: {', '.join(_BACKENDS)}"
        )
    missing: list[str] = []
    if backend == "gcs" and not (config.GCS_KEY and config.GCS_SECRET):
        missing = ["NILA_GCS_KEY", "NILA_GCS_SECRET"]
    elif backend == "r2" and not (config.R2_ACCOUNT_ID and config.R2_KEY and config.R2_SECRET):
        missing = ["NILA_R2_ACCOUNT_ID", "NILA_R2_KEY", "NILA_R2_SECRET"]
    elif backend == "azure":
        if config.AZURE_AUTH == "connection_string" and not config.AZURE_CONNECTION_STRING:
            missing = ["NILA_AZURE_CONNECTION_STRING"]
        elif config.AZURE_AUTH != "connection_string" and not config.AZURE_ACCOUNT:
            missing = ["NILA_AZURE_ACCOUNT"]
    if missing:
        raise SystemExit(f"[nilalytics] storage '{backend}' needs: {', '.join(missing)}")


def configure(con) -> str:
    """Load extension(s), register the storage secret, return the DuckLake DATA_PATH."""
    _validate()
    backend = _BACKENDS[config.STORAGE]
    for ext in backend["exts"]:
        con.execute(f"INSTALL {ext}; LOAD {ext};")
    con.execute(backend["secret"]())
    return backend["path"]()
