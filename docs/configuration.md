# Configuration

Everything is configured with environment variables. Defaults target a local
MinIO dev setup, so `nilalytics server` works out of the box.

## Core

| Variable | Default | Description |
|----------|---------|-------------|
| `NILA_DATA_DIR` | `~/.nilalytics` | Writable dir for the catalog file + secrets |
| `NILA_STORAGE` | `s3` | Object storage backend: `s3` \| `gcs` \| `r2` \| `azure` |
| `NILA_BUCKET` | `nilalytics` | Bucket (or Azure **container**) |
| `NILA_PREFIX` | `lake` | Key prefix within the bucket |
| `NILA_CATALOG` | `<data dir>/catalog.ducklake` | DuckLake catalog file |
| `NILA_INLINE_LIMIT` | `1000` | Inserts smaller than this stay inlined (no Parquet file) |
| `NILA_ENV` | `production` | `deployment.environment` sent by the sample emitter |

## Object storage

### S3 / MinIO / S3‑compatible
| Variable | Default | Notes |
|----------|---------|-------|
| `NILA_S3_ENDPOINT` | `127.0.0.1:9100` | Leave **empty** for real AWS S3 |
| `NILA_S3_KEY` / `NILA_S3_SECRET` | `minioadmin` | Access key / secret |
| `NILA_S3_SESSION_TOKEN` | – | Optional STS token |
| `NILA_S3_USE_SSL` | `false` | Set `true` for remote |
| `NILA_S3_URL_STYLE` | `path` | `path` (MinIO/R2) or `vhost` |
| `NILA_S3_REGION` | `us-east-1` | Bucket region |

### Google Cloud Storage
| Variable | Notes |
|----------|-------|
| `NILA_GCS_KEY` / `NILA_GCS_SECRET` | HMAC interoperability keys |

### Cloudflare R2
| Variable | Notes |
|----------|-------|
| `NILA_R2_ACCOUNT_ID`, `NILA_R2_KEY`, `NILA_R2_SECRET` | R2 S3 token |

### Azure / ADLS Gen2
| Variable | Notes |
|----------|-------|
| `NILA_AZURE_ACCOUNT` | Storage account name |
| `NILA_AZURE_AUTH` | `credential_chain` (default) \| `connection_string` \| `service_principal` |
| `NILA_AZURE_CONNECTION_STRING` | for `connection_string` |
| `NILA_AZURE_TENANT_ID` / `NILA_AZURE_CLIENT_ID` / `NILA_AZURE_CLIENT_SECRET` | for `service_principal` |

See [Storage backends](storage-backends.md) for full examples.

## Ingest (OTLP server)

| Variable | Default | Description |
|----------|---------|-------------|
| `NILA_OTLP_URI` | `otlp:127.0.0.1:4318` | Internal OTLP listen URI |
| `NILA_OTLP_HTTP` | `http://127.0.0.1:4318` | Internal OTLP base URL |
| `NILA_OTLP_TOKEN` | *(generated)* | Internal ingest token (never leaves the host with the gateway) |

## Tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `NILA_SEAL_MAX_AGE_MS` | `1000` | Commit freshness |
| `NILA_RETENTION_MS` | 7 days | Snapshot/file retention |
| `NILA_PROMOTE_RESOURCE_ATTRS` | `deployment.environment` | Resource attrs promoted to columns |
| `NILA_PARTITION_BY` | `day(time_unix_nano)` | DuckLake partition transform |
| `NILA_SORTED_BY` | `body, time_unix_nano` | DuckLake sort order |

## Curated `user_events`

The server keeps a curated per‑user table for recommendations / ML — see
[User events](user-events.md).

| Variable | Default | Description |
|----------|---------|-------------|
| `NILA_USER_EVENTS` | `true` | Build + refresh the curated `user_events` table |
| `NILA_USER_EVENTS_TABLE` | `user_events` | Curated table name |
| `NILA_USER_EVENTS_REFRESH_SECONDS` | `60` | How often the server appends new rows |
| `NILA_USER_EVENTS_PARTITION_BY` | `day(event_time)` | Partition (keep **low‑cardinality**) |
| `NILA_USER_EVENTS_SORTED_BY` | `person_id, event_time_unix_nano` | Cluster by person for fast per‑user reads |

## Data retention

Delete **event rows** older than a cutoff so storage stays bounded (opt‑in) — see
[Maintenance → Data retention](maintenance.md#data-retention-dont-grow-forever).

| Variable | Default | Description |
|----------|---------|-------------|
| `NILA_RETENTION_DAYS` | `0` (off) | Delete events older than N days from every event table |
| `NILA_RETENTION_INTERVAL_SECONDS` | `3600` | How often the server runs the retention sweep |

!!! warning "Two different retentions"
    `NILA_RETENTION_DAYS` drops **event rows** (the data). `NILA_RETENTION_MS`
    (under *Tuning*) drops **snapshots / old files** (time‑travel history). They are
    independent.

## Read path (Quack)

| Variable | Default | Description |
|----------|---------|-------------|
| `NILA_QUACK_URI` | `quack:localhost` | Quack listen URI (default port 9494) |
| `NILA_QUACK_TOKEN` | *(generated)* | Token clients present to read |

## Identity

| Variable | Default | Description |
|----------|---------|-------------|
| `NILA_ID_SALT` | *(generated)* | Salt for hashing person keys |

## Gateway

| Variable | Default | Description |
|----------|---------|-------------|
| `NILA_GATEWAY_HOST` | `127.0.0.1` | Set `0.0.0.0` to accept real devices/browsers |
| `NILA_GATEWAY_PORT` | `4319` | Listen port |
| `NILA_GATEWAY_CORS` | `*` | Allowed CORS origin(s) |
| `NILA_GATEWAY_CERT` / `NILA_GATEWAY_KEY` | – | Optional TLS cert/key (else run behind a proxy) |
| `NILA_GATEWAY_SECRET` | *(generated)* | HMAC signing key for short‑lived tokens |
| `NILA_GATEWAY_TOKEN_TTL` | `900` | Token lifetime (seconds) |
| `NILA_INGEST_KEY` | *(generated)* | Rotatable key clients use to mint tokens |

!!! info "Generated secrets"
    Values marked *(generated)* are created on first run and stored in
    `<data dir>/.nila_secrets.json` (mode `0600`). Set them explicitly in
    production and manage rotation yourself.
