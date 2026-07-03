# Install

## Requirements

- **Python 3.11+**
- **Object storage** — one of: local MinIO, AWS S3, Google Cloud Storage, Cloudflare R2, or Azure / ADLS Gen2.
- Network access on first run so DuckDB can auto‑install its extensions
  (`ducklake`, `quack`, `otlp`, `httpfs`/`azure`). No manual extension setup needed.

## Install the package

=== "pip"

    ```bash
    pip install git+https://github.com/Angelerator/nilalytics
    ```

=== "uv"

    ```bash
    uv add git+https://github.com/Angelerator/nilalytics
    # or, inside a clone:
    uv sync
    ```

This installs the `nilalytics` command:

```bash
nilalytics --help
```

```
usage: nilalytics <command> [args]

commands:
  server                      run the ingest + Quack catalog server
  gateway                     run the public ingest gateway (CORS, short-lived tokens, TLS)
  emit [options]              send sample logs/traces/metrics (--persons for cross-device)
  query [subcommand] [args]   report | traces | metrics | stitch | asof | changes | snapshots | errors
  maintenance [--expire]      flush inlined data to Parquet + compact
```

## Local object storage (for development)

The fastest way to try nilalytics is a local MinIO:

```bash
# macOS
brew install minio/stable/minio minio/stable/mc

# start MinIO + create a bucket
minio server .minio-data --address 127.0.0.1:9100 --console-address 127.0.0.1:9101 &
mc alias set nila http://127.0.0.1:9100 minioadmin minioadmin
mc mb --ignore-existing nila/nilalytics
```

The default configuration points at exactly this MinIO (`127.0.0.1:9100`, bucket
`nilalytics`), so nothing else is needed to start. For a real cloud, see
[Storage backends](storage-backends.md).

## Where nilalytics stores its state

- **Catalog + secrets** live in a data directory, default `~/.nilalytics`
  (override with `NILA_DATA_DIR`). This is independent of where the package is
  installed, so `nilalytics` works from any directory.
- **Event data** lives in your object storage bucket.

Next: the [Quickstart](quickstart.md).
