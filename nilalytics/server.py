"""nilalytics server: the single writer process.

One DuckDB process that:
  1. attaches a DuckLake whose data lives on object storage (MinIO now, R2 later)
     and whose catalog is a local DuckDB file (served to clients via Quack),
  2. runs an OTLP/HTTP ingest endpoint (duckdb-otlp) that streams events straight
     into the DuckLake (small batches are inlined, so no tiny-file churn),
  3. serves the same DuckLake to clients over the Quack protocol (the read path
     used by dashboards / DuckDB-WASM), so clients never touch object storage
     credentials directly.

Run it:  uv run python -m nilalytics.server
Stop it: Ctrl-C (commits buffered rows, then stops cleanly).
"""

from __future__ import annotations

import signal
import time

import duckdb

from . import config, storage


def _install_quack_authz(con: duckdb.DuckDBPyConnection) -> None:
    """Block destructive statements from Quack clients (read/observe only).

    Quack clients (dashboards, DuckDB-WASM) may query and run maintenance
    functions, but cannot mutate rows or attach external databases. The server's
    own connection is not a Quack client, so ingest and layout are unaffected.
    """
    con.execute(
        r"""
        CREATE OR REPLACE MACRO nila_authz(sid, query) AS
          NOT regexp_matches(
            upper(query),
            '\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|TRUNCATE|REPLACE|COPY|EXPORT|INSTALL|LOAD)\b'
          );
        """
    )
    con.execute("SET GLOBAL quack_authorization_function = 'nila_authz';")


def _apply_layout(con: duckdb.DuckDBPyConnection) -> None:
    """Partition + sort the events table for fast time/event-filtered queries."""
    for stmt in (
        f"ALTER TABLE {config.LAKE}.main.otlp_logs SET PARTITIONED BY ({config.PARTITION_BY})",
        f"ALTER TABLE {config.LAKE}.main.otlp_logs SET SORTED BY ({config.SORTED_BY})",
    ):
        try:
            con.execute(stmt)
        except Exception as exc:  # noqa: BLE001 - non-fatal; table may lag on first boot
            print(f"[nilalytics] layout warning: {exc}", flush=True)


def build_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()  # in-memory control DB; the lake is attached below
    con.execute("INSTALL ducklake; LOAD ducklake;")
    con.execute("INSTALL quack FROM core_nightly; LOAD quack;")
    con.execute("INSTALL otlp FROM community; LOAD otlp;")

    _install_quack_authz(con)

    # Load the storage extension + register credentials for the selected cloud
    # (s3/gcs/r2/azure); returns the DuckLake DATA_PATH URI.
    data_path = storage.configure(con)

    con.execute(
        f"""
        ATTACH 'ducklake:{config.CATALOG_PATH}' AS {config.LAKE} (
            DATA_PATH '{data_path}',
            DATA_INLINING_ROW_LIMIT {config.DATA_INLINING_ROW_LIMIT}
        );
        """
    )
    return con


def start_servers(con: duckdb.DuckDBPyConnection) -> str:
    # OTLP ingest -> DuckLake. create_tables (default true) creates the six
    # otlp_* tables inside the lake on first start.
    promote = config.PROMOTE_RESOURCE_ATTRS.strip()
    promote_clause = (
        f", promote_resource_attributes := '{promote}'" if promote else ""
    )
    otlp_url = con.execute(
        f"""
        SELECT listen_url
        FROM otlp_serve('{config.OTLP_URI}',
                        catalog := '{config.LAKE}',
                        token := '{config.OTLP_TOKEN}',
                        seal_max_age_ms := {config.SEAL_MAX_AGE_MS},
                        maintenance_retention_ms := {config.MAINTENANCE_RETENTION_MS}{promote_clause});
        """
    ).fetchone()[0]

    # Physical layout for query speed (partition by day, sort by event+time).
    _apply_layout(con)

    # Quack read server: exposes this process's databases (incl. the lake) to
    # clients over HTTP. disable_ssl for localhost.
    con.execute(
        f"""
        CALL quack_serve('{config.QUACK_URI}',
                         token => '{config.QUACK_TOKEN}',
                         allow_other_hostname => false,
                         disable_ssl => true);
        """
    )
    return otlp_url


def main(argv=None) -> None:  # argv accepted for CLI compatibility (unused)
    config.assert_safe()
    con = build_connection()
    otlp_url = start_servers(con)

    print(f"[nilalytics] OTLP ingest ready:  {otlp_url}/v1/logs (auth: Bearer token required)", flush=True)
    print(f"[nilalytics] Quack catalog ready: {config.QUACK_URI} (token required)", flush=True)
    print(f"[nilalytics] storage backend:     {config.STORAGE} -> {storage.data_path()}", flush=True)
    print(f"[nilalytics] secrets file:         {config._SECRETS_FILE}", flush=True)
    print("[nilalytics] READY", flush=True)

    stop = {"flag": False}

    def _handle(_sig, _frame):
        stop["flag"] = True

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    try:
        while not stop["flag"]:
            time.sleep(0.5)
    finally:
        # Commit buffered rows and release ports.
        try:
            con.execute(f"SELECT * FROM otlp_stop('{config.OTLP_URI}');")
        except Exception as exc:  # noqa: BLE001 - best-effort shutdown
            print(f"[nilalytics] otlp_stop error: {exc}", flush=True)
        try:
            con.execute(f"CALL quack_stop('{config.QUACK_URI}');")
        except Exception as exc:  # noqa: BLE001 - best-effort shutdown
            print(f"[nilalytics] quack_stop error: {exc}", flush=True)
        con.close()
        print("[nilalytics] stopped", flush=True)


if __name__ == "__main__":
    main()
