"""nilalytics curation: a per-user events table for recommendations / ML.

``otlp_logs`` is optimised for *ingest*: it is date-partitioned and keeps identity
(``user.id`` / ``anonymous.id`` / ``session.id``) inside a JSON attributes column.
That is great for streaming, but slow for the core recommendation read — "give me
everything this person did".

This module maintains a curated ``user_events`` table that:

* lifts identity + the common event fields into typed, first-class columns;
* classifies each event into a low-cardinality ``subject`` (errors / activities /
  ai_usage / traceability / other) and is partitioned by ``(subject, day)`` — both
  low-cardinality — and **SORTED BY ``person_id``**, so reads prune subject -> day ->
  person without the partition-per-user tiny-file explosion that keying the
  *partition* on ``user_id`` would cause;
* is refreshed **incrementally** via the DuckLake change feed, so each run only
  processes rows committed since the previous run (order-safe: late/out-of-order
  events are still picked up, because the watermark is a snapshot id, not a
  timestamp).

It runs inside the server process — the single writer that owns the catalog — so
the Quack read path stays strictly read-only. See ``server.py``.
"""

from __future__ import annotations

import duckdb

from . import config

# The canonical, LOW-cardinality subjects. Because `subject` is a PARTITION key, we
# clamp every value to this set so a stray tag can never explode the partitions.
SUBJECTS = ("errors", "activities", "ai_usage", "traceability", "other")

# Raw subject: an explicit `nila.subject` attribute wins; otherwise it's derived
# from the event's shape (severity/exception -> errors, gen_ai/llm -> ai_usage,
# identify/audit -> traceability, everything else -> activities).
_SUBJECT_RAW = """coalesce(
    json_extract_string(log_attributes, '$."nila.subject"'),
    CASE
      WHEN severity_text = 'ERROR'
           OR json_extract_string(log_attributes, '$."exception.type"') IS NOT NULL
        THEN 'errors'
      WHEN json_extract_string(log_attributes, '$."gen_ai.system"') IS NOT NULL
           OR json_extract_string(log_attributes, '$."gen_ai.request.model"') IS NOT NULL
           OR json_extract_string(log_attributes, '$."llm.model"') IS NOT NULL
        THEN 'ai_usage'
      WHEN body = 'identify'
           OR json_extract_string(log_attributes, '$."audit.action"') IS NOT NULL
        THEN 'traceability'
      ELSE 'activities'
    END
  )"""

# Clamp to the known set (anything else -> 'other') to keep the partition bounded.
_SUBJECT = (
    f"CASE WHEN ({_SUBJECT_RAW}) IN ('errors','activities','ai_usage','traceability') "
    f"THEN ({_SUBJECT_RAW}) ELSE 'other' END"
)

# The fields we lift out of otlp_logs into typed columns. This projection is valid
# both over the base table and over the change feed (both expose the same base
# columns). event_time is derived in UTC from the epoch-ns timestamp via microsecond
# precision; event_time_unix_nano keeps exact ordering.
_SELECT = f"""
  make_timestamp(CAST(time_unix_nano / 1000 AS BIGINT)) AS event_time,
  time_unix_nano AS event_time_unix_nano,
  {_SUBJECT} AS subject,
  body AS event,
  json_extract_string(log_attributes, '$."user.id"') AS user_id,
  json_extract_string(log_attributes, '$."anonymous.id"') AS anonymous_id,
  json_extract_string(log_attributes, '$."session.id"') AS session_id,
  coalesce(json_extract_string(log_attributes, '$."user.id"'),
           json_extract_string(log_attributes, '$."anonymous.id"')) AS person_id,
  json_extract_string(log_attributes, '$."page"') AS page,
  severity_text,
  service_name,
  CAST(log_attributes AS VARCHAR) AS attributes
"""

_COLS = (
    "(event_time, event_time_unix_nano, subject, event, user_id, anonymous_id, "
    "session_id, person_id, page, severity_text, service_name, attributes)"
)

_SOURCE = "otlp_logs"  # the raw table we curate from


def _columns(con: duckdb.DuckDBPyConnection, table: str) -> set[str]:
    rows = con.execute(
        "SELECT column_name FROM information_schema.columns "
        f"WHERE table_catalog = '{config.LAKE}' AND table_schema = 'main' AND table_name = '{table}'"
    ).fetchall()
    return {r[0] for r in rows}


def ensure(con: duckdb.DuckDBPyConnection) -> None:
    """Create the curated table + watermark state, and apply the physical layout.

    Idempotent: safe to call on every server start. If a pre-`subject` table exists
    (from an earlier version), it is dropped and the watermark reset so refresh()
    rebuilds it with subjects -- safe because the table is fully derived from
    otlp_logs, which is the source of truth.
    """
    lake, tbl = config.LAKE, config.USER_EVENTS_TABLE
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {lake}.main.nila_curate_state (
            source        VARCHAR,
            last_snapshot BIGINT
        );
        """
    )

    existing = _columns(con, tbl)
    if existing and "subject" not in existing:
        # Migrate: rebuild the derived table with the new schema/layout.
        con.execute(f"DROP TABLE {lake}.main.{tbl};")
        con.execute(f"DELETE FROM {lake}.main.nila_curate_state WHERE source = '{_SOURCE}';")
        print(f"[nilalytics] user_events migrated: rebuilding with 'subject' partition", flush=True)

    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {lake}.main.{tbl} (
            event_time            TIMESTAMP,
            event_time_unix_nano  BIGINT,
            subject               VARCHAR,
            event                 VARCHAR,
            user_id               VARCHAR,
            anonymous_id          VARCHAR,
            session_id            VARCHAR,
            person_id             VARCHAR,
            page                  VARCHAR,
            severity_text         VARCHAR,
            service_name          VARCHAR,
            attributes            VARCHAR
        );
        """
    )
    for stmt in (
        f"ALTER TABLE {lake}.main.{tbl} SET PARTITIONED BY ({config.USER_EVENTS_PARTITION_BY})",
        f"ALTER TABLE {lake}.main.{tbl} SET SORTED BY ({config.USER_EVENTS_SORTED_BY})",
    ):
        try:
            con.execute(stmt)
        except Exception as exc:  # noqa: BLE001 - non-fatal; layout is a hint
            print(f"[nilalytics] user_events layout warning: {exc}", flush=True)


def _current_snapshot(con: duckdb.DuckDBPyConnection):
    return con.execute(f"SELECT max(snapshot_id) FROM {config.LAKE}.snapshots()").fetchone()[0]


def _last_snapshot(con: duckdb.DuckDBPyConnection):
    row = con.execute(
        f"SELECT last_snapshot FROM {config.LAKE}.main.nila_curate_state WHERE source = '{_SOURCE}'"
    ).fetchone()
    return row[0] if row else None


def refresh(con: duckdb.DuckDBPyConnection) -> int:
    """Append rows committed since the last run into the curated table.

    Returns the number of rows added. Atomic: the watermark only advances if the
    insert commits, so a failure simply retries the same range next time (no gaps,
    no duplicates).
    """
    lake, tbl = config.LAKE, config.USER_EVENTS_TABLE
    cur = _current_snapshot(con)
    if cur is None:
        return 0
    last = _last_snapshot(con)
    if last is not None and cur <= last:
        return 0  # nothing new committed

    if last is None:
        # First run: a consistent full backfill of everything as of snapshot `cur`.
        source = f"{lake}.main.{_SOURCE} AT (VERSION => {cur})"
        where = ""
    else:
        # Incremental: only rows inserted in (last, cur]. A snapshot-id watermark
        # (not a timestamp) means late-arriving events are never missed.
        source = f"{lake}.table_changes('{_SOURCE}', {last + 1}, {cur})"
        where = "WHERE change_type = 'insert'"

    con.execute("BEGIN TRANSACTION;")
    try:
        inserted = con.execute(
            f"INSERT INTO {lake}.main.{tbl} {_COLS} SELECT {_SELECT} FROM {source} {where}"
        ).fetchone()[0]
        con.execute(f"DELETE FROM {lake}.main.nila_curate_state WHERE source = '{_SOURCE}';")
        con.execute(f"INSERT INTO {lake}.main.nila_curate_state VALUES ('{_SOURCE}', {cur});")
        con.execute("COMMIT;")
    except Exception:
        con.execute("ROLLBACK;")
        raise
    return int(inserted or 0)
