"""nilalytics data retention: drop events older than a cutoff so storage is bounded.

This is **event/row retention** — it deletes old rows from the event tables. It is
separate from DuckLake's *snapshot* retention (``NILA_RETENTION_MS``), which governs
how long time-travel history + old files are kept.

How storage actually shrinks:

1. This sweep ``DELETE``s rows older than ``NILA_RETENTION_DAYS`` (a new snapshot).
2. The underlying Parquet files are reclaimed when the old snapshots expire — the
   ingest server does this automatically within its snapshot-retention window, and
   ``nilalytics maintenance --expire`` forces it on demand.

It runs inside the server process (the single writer that owns the catalog), so the
Quack read path stays read-only. Row retention is **opt-in** (default disabled): set
``NILA_RETENTION_DAYS`` to a positive number to turn it on.

Design notes:

* We delete by the epoch-nanosecond time column (a plain ``BIGINT`` compare), which is
  cheap and prunes by day-partition — the opposite end of the table from the hot rows
  the ingest server is writing, so the two writers don't fight over the same files.
* Each table is swept independently and guarded, so a table that doesn't exist (or
  uses a different time column) is skipped rather than failing the whole sweep.
"""

from __future__ import annotations

import time

import duckdb

from . import config

# (table, epoch-nanosecond time column). Curated user_events uses its own column.
_TABLES: tuple[tuple[str, str], ...] = (
    ("otlp_logs", "time_unix_nano"),
    ("otlp_traces", "start_time_unix_nano"),
    ("otlp_metrics_gauge", "time_unix_nano"),
    ("otlp_metrics_sum", "time_unix_nano"),
    (config.USER_EVENTS_TABLE, "event_time_unix_nano"),
)


def _cutoff_ns(days: int) -> int:
    """Epoch-nanosecond timestamp `days` in the past."""
    return int((time.time() - days * 86_400) * 1_000_000_000)


def plan(days: int | None = None) -> list[tuple[str, str, int]]:
    """The retention plan: [(table, time_column, cutoff_ns)].

    Both the server-side sweep and the read-only dry-run preview build from this,
    so "what gets deleted" is defined in exactly one place. A non-positive window
    (the default when retention is disabled) yields an empty plan.
    """
    days = config.RETENTION_DAYS if days is None else days
    if not days or days <= 0:
        return []
    cutoff = _cutoff_ns(days)
    return [(tbl, col, cutoff) for tbl, col in _TABLES]


def existing_tables(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Tables that actually exist in the lake's main schema (varies per deployment)."""
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables "
        f"WHERE table_catalog = '{config.LAKE}' AND table_schema = 'main'"
    ).fetchall()
    return {r[0] for r in rows}


def sweep(con: duckdb.DuckDBPyConnection, days: int | None = None) -> dict[str, int]:
    """Delete rows older than `days` from each event table. Returns {table: deleted}.

    A non-positive `days` (the default) is a no-op, so this is safe to call
    unconditionally from the server loop. Tables absent in this deployment are
    skipped silently; a real error (e.g. a schema mismatch) is logged.
    """
    items = plan(days)
    if not items:
        return {}

    present = existing_tables(con)
    deleted: dict[str, int] = {}
    for tbl, col, cutoff in items:
        if tbl not in present:
            continue
        try:
            n = con.execute(
                f"DELETE FROM {config.LAKE}.main.{tbl} WHERE {col} < {cutoff}"
            ).fetchone()[0]
            if n:
                deleted[tbl] = int(n)
        except Exception as exc:  # noqa: BLE001 - unexpected schema mismatch
            print(f"[nilalytics] retention skip {tbl}: {exc}", flush=True)
    return deleted
