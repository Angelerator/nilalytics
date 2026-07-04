"""nilalytics maintenance: flush inlined rows to Parquet and compact.

Streaming events accumulate as inlined rows inside the catalog (fast, no small
files). Periodically we materialise them into object-storage Parquet and merge
small files. duckdb-otlp already runs this automatically after seals; this module
lets you trigger and observe it on demand.

Run it:  uv run python -m nilalytics.maintenance
"""

from __future__ import annotations

import argparse

from . import config, retention
from .query import connect, flush, rq


def run(con, expire: bool = False) -> None:
    flush(con)  # make sure buffered OTLP rows are committed first

    print("flush inlined data -> Parquet on object storage:")
    for row in rq(con, f"CALL ducklake_flush_inlined_data('{config.LAKE}')").fetchall():
        print("  ", row)

    print("merge adjacent files (compaction):")
    merged = rq(con, f"CALL ducklake_merge_adjacent_files('{config.LAKE}')").fetchall()
    if merged:
        for row in merged:
            print("  ", row)
    else:
        print("   (nothing to merge)")

    # Expiring snapshots + deleting files is destructive to time-travel history,
    # so it is opt-in. The ingest server also runs bounded auto-maintenance.
    if expire:
        print("expire old snapshots + clean orphaned files (destructive):")
        rq(con, f"CALL ducklake_expire_snapshots('{config.LAKE}', older_than => now())").fetchall()
        rq(con, f"CALL ducklake_cleanup_old_files('{config.LAKE}', cleanup_all => true)").fetchall()
        print("   done")

    total = rq(con, "SELECT count(*) FROM lake.main.otlp_logs").fetchone()[0]
    print(f"rows after maintenance: {total}")

    # The curated user_events table is compacted by the same flush/merge above
    # (they operate on the whole lake); report its size for visibility.
    try:
        curated = rq(con, f"SELECT count(*) FROM lake.main.{config.USER_EVENTS_TABLE}").fetchone()[0]
        print(f"curated {config.USER_EVENTS_TABLE} rows: {curated}")
    except Exception:  # noqa: BLE001 - table absent if curation is disabled
        pass


def retention_preview(con, days: int | None = None) -> None:
    """Read-only: report how many rows retention WOULD delete, per table.

    Runs over the Quack read path (no deletes) so operators can size the window
    before enabling `NILA_RETENTION_DAYS`. The actual deletion runs inside the
    server (the single writer); see nilalytics/retention.py.
    """
    days = config.RETENTION_DAYS if days is None else days
    items = retention.plan(days)
    if not items:
        print("retention window is 0 (disabled). Pass --days N to preview a window.")
        return

    existing = {
        r[0]
        for r in rq(
            con,
            "SELECT table_name FROM information_schema.tables "
            f"WHERE table_catalog = '{config.LAKE}' AND table_schema = 'main'",
        ).fetchall()
    }
    print(f"retention dry-run: rows older than {days} days (nothing is deleted)")
    total = 0
    for tbl, col, cutoff in items:
        if tbl not in existing:
            continue
        n = rq(con, f"SELECT count(*) FROM {config.LAKE}.main.{tbl} WHERE {col} < {cutoff}").fetchone()[0]
        total += n
        print(f"  {tbl:<22} {n}")
    print(f"  total rows that would be deleted: {total}")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="nilalytics maintenance",
                                     description="Flush inlined data to Parquet and compact.")
    parser.add_argument("--expire", action="store_true",
                        help="also expire old snapshots + delete unused files (destructive)")
    parser.add_argument("--retention-dry-run", action="store_true",
                        help="report rows that data retention WOULD delete (read-only, no deletes)")
    parser.add_argument("--days", type=int, default=None,
                        help="retention window (days) to preview with --retention-dry-run")
    args = parser.parse_args(argv)
    con = connect()
    try:
        if args.retention_dry_run:
            flush(con)
            retention_preview(con, args.days)
        else:
            run(con, expire=args.expire)
    finally:
        con.close()


if __name__ == "__main__":
    main()
