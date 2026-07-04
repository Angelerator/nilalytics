# Maintenance

nilalytics keeps streaming writes cheap by **inlining** small batches into the
catalog. Maintenance materializes those into Parquet and compacts them.

## What runs automatically

The ingest server runs **best‑effort compaction** after commits (a bounded
`CHECKPOINT`), so for many workloads you don't need to do anything.

## Manual maintenance

```bash
nilalytics maintenance            # safe: flush inlined rows -> Parquet + merge small files
nilalytics maintenance --expire   # also expire old snapshots + delete unused files (destructive)
```

- **flush** — `ducklake_flush_inlined_data`: move inlined rows into Parquet on object storage.
- **merge** — `ducklake_merge_adjacent_files`: combine small Parquet files.
- **expire/cleanup** (only with `--expire`) — remove old snapshots and unreferenced files. This drops time‑travel history, so it's opt‑in.

## Schedule it

Run compaction periodically (cron / systemd timer / K8s CronJob):

```bash
# every 15 minutes
*/15 * * * * NILA_DATA_DIR=/var/lib/nilalytics /usr/local/bin/nilalytics maintenance
```

## Data retention (don't grow forever)

Two different "retentions" — don't confuse them:

| Knob | What it drops | Default |
|------|---------------|---------|
| **`NILA_RETENTION_DAYS`** | **event rows** older than N days (the data itself) | `0` = off |
| `NILA_RETENTION_MS` | DuckLake **snapshots / old files** (time‑travel history) | 7 days |

Turn on event retention by setting a positive number of days:

```bash
NILA_RETENTION_DAYS=90               # keep 90 days of events
NILA_RETENTION_INTERVAL_SECONDS=3600 # sweep hourly (default)
```

**How it works (and how storage actually shrinks):**

1. The **server** deletes rows older than the cutoff from every event table
   (`otlp_logs`, `otlp_traces`, `otlp_metrics_*`, and the curated `user_events`).
   This is a delete‑only sweep — it runs inside the single‑writer server, so the
   read path stays read‑only.
2. Deleting rows writes a new snapshot; the **old Parquet files are reclaimed when
   the snapshots expire** — automatically within `NILA_RETENTION_MS`, or on demand
   with `nilalytics maintenance --expire`.

!!! warning "Destructive + opt‑in"
    Event retention permanently deletes data, so it is **off by default**. It
    deletes by day, at the cold end of the table, so it doesn't fight the hot
    writes the ingest server is doing.

## Retention & freshness knobs

Set as environment variables (see [Configuration](configuration.md)):

- `NILA_SEAL_MAX_AGE_MS` (default `1000`) — how quickly buffered rows commit. Lower = fresher, more files.
- `NILA_RETENTION_MS` (default 7 days) — how long **snapshots / old files** are kept before reclaim.
- `NILA_RETENTION_DAYS` (default `0` = off) — delete **event rows** older than N days (see above).
- `NILA_INLINE_LIMIT` (default `1000`) — inserts smaller than this stay inlined (no Parquet file).

## Observe it

```bash
nilalytics query snapshots   # snapshot history
```

Inlined rows live in the catalog; flushed data lives as Parquet in your bucket —
you can list the bucket to see files appear after a flush.
