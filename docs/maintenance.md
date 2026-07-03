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

## Retention & freshness knobs

Set as environment variables (see [Configuration](configuration.md)):

- `NILA_SEAL_MAX_AGE_MS` (default `1000`) — how quickly buffered rows commit. Lower = fresher, more files.
- `NILA_RETENTION_MS` (default 7 days) — how long snapshots / old files are kept before reclaim.
- `NILA_INLINE_LIMIT` (default `1000`) — inserts smaller than this stay inlined (no Parquet file).

## Observe it

```bash
nilalytics query snapshots   # snapshot history
```

Inlined rows live in the catalog; flushed data lives as Parquet in your bucket —
you can list the bucket to see files appear after a flush.
