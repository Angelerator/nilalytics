"""nilalytics maintenance: flush inlined rows to Parquet and compact.

Streaming events accumulate as inlined rows inside the catalog (fast, no small
files). Periodically we materialise them into object-storage Parquet and merge
small files. duckdb-otlp already runs this automatically after seals; this module
lets you trigger and observe it on demand.

Run it:  uv run python -m nilalytics.maintenance
"""

from __future__ import annotations

import argparse

from . import config
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


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="nilalytics maintenance",
                                     description="Flush inlined data to Parquet and compact.")
    parser.add_argument("--expire", action="store_true",
                        help="also expire old snapshots + delete unused files (destructive)")
    args = parser.parse_args(argv)
    con = connect()
    try:
        run(con, expire=args.expire)
    finally:
        con.close()


if __name__ == "__main__":
    main()
