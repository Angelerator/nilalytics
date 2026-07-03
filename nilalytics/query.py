"""nilalytics query client: reads the DuckLake over the Quack protocol.

This is the read path a dashboard (or DuckDB-WASM in the browser) would use: it
never touches object storage or the catalog file directly. It connects to the
Quack server and ships SQL to it via ``remote.query(...)``, which runs on the
server where the DuckLake is attached.

Run it:  uv run python -m nilalytics.query report
         uv run python -m nilalytics.query schema
         uv run python -m nilalytics.query flush
"""

from __future__ import annotations

import sys
import time

import duckdb

from . import config


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("INSTALL quack FROM core_nightly; LOAD quack;")
    con.execute(f"CREATE OR REPLACE SECRET quack_auth (TYPE quack, TOKEN '{config.QUACK_TOKEN}');")
    con.execute(f"ATTACH '{config.QUACK_URI}' AS remote;")
    return con


def rq(con: duckdb.DuckDBPyConnection, sql: str):
    """Ship a verbatim query to the Quack server (where the lake is attached)."""
    escaped = sql.replace("'", "''")
    return con.execute(f"SELECT * FROM remote.query('{escaped}')")


def flush(con: duckdb.DuckDBPyConnection) -> None:
    """Force buffered OTLP rows to commit so reads see the latest data."""
    rows = rq(con, f"SELECT * FROM otlp_flush('{config.OTLP_URI}')").fetchall()
    print("flush:", rows)


def schema(con: duckdb.DuckDBPyConnection) -> None:
    print("== DESCRIBE lake.main.otlp_logs ==")
    for row in rq(con, "DESCRIBE lake.main.otlp_logs").fetchall():
        print("  ", row)


def count(con: duckdb.DuckDBPyConnection) -> None:
    n = rq(con, "SELECT count(*) FROM lake.main.otlp_logs").fetchone()[0]
    print("total otlp_logs rows:", n)


USER_ID = "json_extract_string(log_attributes, '$.\"user.id\"')"
ANON = "json_extract_string(log_attributes, '$.\"anonymous.id\"')"
PAGE = "json_extract_string(log_attributes, '$.\"page\"')"


def sample(con: duckdb.DuckDBPyConnection) -> None:
    print("== one raw row ==")
    row = rq(con, "SELECT body, severity_text, log_attributes FROM lake.main.otlp_logs LIMIT 1").fetchone()
    print("  ", row)


def errors(con: duckdb.DuckDBPyConnection) -> None:
    print("recent errors:")
    rows = rq(
        con,
        "SELECT time_unix_nano, service_name, "
        "json_extract_string(log_attributes, '$.\"exception.type\"') AS t, "
        "json_extract_string(log_attributes, '$.\"exception.message\"') AS m "
        "FROM lake.main.otlp_logs WHERE severity_text = 'ERROR' "
        "ORDER BY time_unix_nano DESC LIMIT 10",
    ).fetchall()
    for ts, svc, etype, emsg in rows:
        print(f"  {ts}  {svc or '-':<18} {etype or '-'}: {emsg or ''}")


def report(con: duckdb.DuckDBPyConnection) -> None:
    flush(con)

    total = rq(con, "SELECT count(*) FROM lake.main.otlp_logs").fetchone()[0]
    print(f"\ntotal events: {total}")

    print("\nby event:")
    for event, c in rq(
        con,
        "SELECT body AS event, count(*) AS c FROM lake.main.otlp_logs GROUP BY 1 ORDER BY c DESC",
    ).fetchall():
        print(f"  {event:<18} {c}")

    errors = rq(con, "SELECT count(*) FROM lake.main.otlp_logs WHERE severity_text = 'ERROR'").fetchone()[0]
    devices = rq(con, f"SELECT count(DISTINCT {ANON}) FROM lake.main.otlp_logs").fetchone()[0]
    identified = rq(
        con, f"SELECT count(DISTINCT {USER_ID}) FROM lake.main.otlp_logs WHERE body = 'identify'"
    ).fetchone()[0]
    starts, completes = rq(
        con,
        "SELECT count(*) FILTER (WHERE body='signup_start') AS s, "
        "count(*) FILTER (WHERE body='signup_complete') AS c FROM lake.main.otlp_logs",
    ).fetchone()
    conv = (completes / starts * 100) if starts else 0.0
    print(f"\ndistinct devices:   {devices}")
    print(f"identified persons: {identified}")
    print(f"errors:             {errors}")
    print(f"signup funnel:      {starts} start -> {completes} complete ({conv:.0f}%)")

    print("\nrecent events:")
    for ts, event, sev, anon, page in rq(
        con,
        f"SELECT time_unix_nano, body, severity_text, {ANON} AS a, {PAGE} AS p "
        "FROM lake.main.otlp_logs ORDER BY time_unix_nano DESC LIMIT 5",
    ).fetchall():
        print(f"  {ts}  {event:<16} {sev:<5} dev:{(anon or '')[:8]}  {page or ''}")

    # Latency: time a representative aggregate over the hot (inlined) data.
    t0 = time.perf_counter()
    rq(
        con,
        f"SELECT {PAGE} AS page, count(*) AS views FROM lake.main.otlp_logs "
        "WHERE body='page_view' GROUP BY 1 ORDER BY views DESC",
    ).fetchall()
    elapsed_ms = (time.perf_counter() - t0) * 1000
    verdict = "SUB-SECOND" if elapsed_ms < 1000 else "over 1s"
    print(f"\naggregate query latency: {elapsed_ms:.1f} ms  [{verdict}]")


def traces(con: duckdb.DuckDBPyConnection) -> None:
    print("recent spans:")
    for ts, name, svc, dur in rq(
        con,
        "SELECT start_time_unix_nano, name, service_name, duration_time_unix_nano "
        "FROM lake.main.otlp_traces ORDER BY start_time_unix_nano DESC LIMIT 5",
    ).fetchall():
        print(f"  {ts}  {name:<14} {svc:<16} {dur / 1e6:.0f} ms")
    print("p95 latency by span:")
    for name, p95, n in rq(
        con,
        "SELECT name, quantile_cont(duration_time_unix_nano, 0.95) / 1e6 AS p95_ms, count(*) c "
        "FROM lake.main.otlp_traces GROUP BY 1 ORDER BY c DESC",
    ).fetchall():
        print(f"  {name:<14} p95={p95:.0f} ms  ({n} spans)")


def metrics(con: duckdb.DuckDBPyConnection) -> None:
    print("metrics (name, count, avg):")
    for name, n, avg in rq(
        con,
        "SELECT name, count(*) c, round(avg(double_value), 1) avg "
        "FROM lake.main.otlp_metrics_gauge GROUP BY 1 ORDER BY c DESC",
    ).fetchall():
        print(f"  {name:<18} n={n} avg={avg}")


def snapshots(con: duckdb.DuckDBPyConnection) -> None:
    print("snapshots (id, time):")
    for sid, t in rq(
        con, "SELECT snapshot_id, snapshot_time FROM lake.snapshots() ORDER BY snapshot_id DESC LIMIT 10"
    ).fetchall():
        print(f"  {sid}  {t}")


def asof(con: duckdb.DuckDBPyConnection, interval: str) -> None:
    """Time travel: compare current row count to the state `interval` ago."""
    total = rq(con, "SELECT count(*) FROM lake.main.otlp_logs").fetchone()[0]
    try:
        past = rq(
            con,
            f"SELECT count(*) FROM lake.main.otlp_logs AT (TIMESTAMP => now() - INTERVAL '{interval}')",
        ).fetchone()[0]
        print(f"log events now: {total} | as of {interval} ago: {past} | new since: {total - past}")
    except duckdb.Error:
        # Requested time predates the first snapshot (nothing existed yet).
        earliest = rq(con, "SELECT min(snapshot_time) FROM lake.snapshots()").fetchone()[0]
        print(f"log events now: {total} | {interval} ago predates history (earliest snapshot: {earliest})")


def changes(con: duckdb.DuckDBPyConnection, start=None, end=None) -> None:
    """Change data feed between two snapshots (activation / reverse-ETL source)."""
    ids = [r[0] for r in rq(con, "SELECT snapshot_id FROM lake.snapshots() ORDER BY snapshot_id").fetchall()]
    if len(ids) < 2:
        print("need at least 2 snapshots for a change feed")
        return
    start = ids[0] if start is None else int(start)
    end = ids[-1] if end is None else int(end)
    print(f"changes in otlp_logs between snapshot {start} and {end}:")
    rows = rq(
        con,
        f"SELECT change_type, count(*) FROM lake.table_changes('otlp_logs', {start}, {end}) GROUP BY 1 ORDER BY 1",
    ).fetchall()
    for change_type, c in rows:
        print(f"  {change_type}: {c}")
    if not rows:
        print("  (no changes)")


def stitch(con: duckdb.DuckDBPyConnection) -> None:
    """Cross-device identity: unify a person's events across devices via identify events."""
    idmap = (
        f"SELECT DISTINCT {ANON} AS anon, {USER_ID} AS uid "
        "FROM lake.main.otlp_logs WHERE body = 'identify'"
    )
    print("person -> devices:")
    multi = 0
    for uid, ndev in rq(
        con,
        f"WITH idmap AS ({idmap}) "
        "SELECT uid, count(DISTINCT anon) AS devices FROM idmap GROUP BY 1 ORDER BY devices DESC, uid LIMIT 10",
    ).fetchall():
        flag = "  <-- multi-device" if ndev > 1 else ""
        multi += ndev > 1
        print(f"  {uid[:16]}...  {ndev} device(s){flag}")
    print(f"persons seen on >1 device: {multi}")

    print("\nunified events per person (summed across their devices):")
    for uid, ev in rq(
        con,
        f"WITH idmap AS ({idmap}), "
        f"ev AS (SELECT {ANON} AS anon FROM lake.main.otlp_logs WHERE body <> 'identify') "
        "SELECT m.uid, count(*) AS events FROM ev JOIN idmap m ON ev.anon = m.anon "
        "GROUP BY 1 ORDER BY events DESC LIMIT 5",
    ).fetchall():
        print(f"  {uid[:16]}...  {ev} events across devices")


def main(argv=None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "report"
    con = connect()
    try:
        if cmd == "flush":
            flush(con)
        elif cmd == "schema":
            flush(con)
            schema(con)
        elif cmd == "count":
            flush(con)
            count(con)
        elif cmd == "sample":
            flush(con)
            sample(con)
        elif cmd == "errors":
            flush(con)
            errors(con)
        elif cmd == "traces":
            flush(con)
            traces(con)
        elif cmd == "metrics":
            flush(con)
            metrics(con)
        elif cmd == "snapshots":
            snapshots(con)
        elif cmd == "stitch":
            flush(con)
            stitch(con)
        elif cmd == "asof":
            flush(con)
            asof(con, argv[1] if len(argv) > 1 else "1 hour")
        elif cmd == "changes":
            flush(con)
            changes(con,
                    argv[1] if len(argv) > 1 else None,
                    argv[2] if len(argv) > 2 else None)
        else:
            report(con)
    finally:
        con.close()


if __name__ == "__main__":
    main()
