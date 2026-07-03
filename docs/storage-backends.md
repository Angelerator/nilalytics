# Storage backends

nilalytics stores Parquet data on object storage. Pick a backend with
`NILA_STORAGE`; the credentials are per‑cloud env vars. Everything else (ingest,
catalog, queries, identity) is identical across clouds.

| `NILA_STORAGE` | Secret type | Path scheme | Extension |
|----------------|-------------|-------------|-----------|
| `s3` | `s3` | `s3://` | httpfs |
| `gcs` | `gcs` | `gs://` | httpfs |
| `r2` | `r2` | `r2://` | httpfs |
| `azure` | `azure` | `abfss://` | azure |

`s3` also covers MinIO and any S3‑compatible store via `NILA_S3_ENDPOINT`.

## AWS S3

```bash
export NILA_STORAGE=s3
export NILA_S3_ENDPOINT=            # empty = real AWS
export NILA_S3_USE_SSL=true
export NILA_S3_KEY=AKIA... NILA_S3_SECRET=...
export NILA_S3_REGION=eu-west-1
export NILA_BUCKET=my-bucket
```

## MinIO (local / self‑hosted)

```bash
export NILA_STORAGE=s3
export NILA_S3_ENDPOINT=127.0.0.1:9100
export NILA_S3_KEY=minioadmin NILA_S3_SECRET=minioadmin
export NILA_BUCKET=nilalytics
```

## Google Cloud Storage

Uses [HMAC interoperability keys](https://cloud.google.com/storage/docs/authentication/managing-hmackeys).

```bash
export NILA_STORAGE=gcs
export NILA_GCS_KEY=GOOG... NILA_GCS_SECRET=...
export NILA_BUCKET=my-bucket
```

## Cloudflare R2

```bash
export NILA_STORAGE=r2
export NILA_R2_ACCOUNT_ID=<33-char account id>
export NILA_R2_KEY=... NILA_R2_SECRET=...
export NILA_BUCKET=my-bucket
```

## Azure / ADLS Gen2

`NILA_BUCKET` is the **container**. Default auth is `credential_chain`
(managed identity on Azure, or `az login` locally).

```bash
export NILA_STORAGE=azure
export NILA_AZURE_ACCOUNT=mystorage
export NILA_BUCKET=events
# credential_chain (default) — nothing else needed if `az login` / managed identity is set up

# or a connection string:
export NILA_AZURE_AUTH=connection_string
export NILA_AZURE_CONNECTION_STRING='DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...'

# or a service principal:
export NILA_AZURE_AUTH=service_principal
export NILA_AZURE_TENANT_ID=... NILA_AZURE_CLIENT_ID=... NILA_AZURE_CLIENT_SECRET=...
```

## Safety guard

For the `s3` backend with a **remote** endpoint, nilalytics refuses to start if
TLS is off or the default `minioadmin` credentials are used. Set
`NILA_S3_USE_SSL=true` and real credentials. GCS/R2/Azure are validated for
required credentials before start.

## Credentials are yours

nilalytics never bundles credentials. Supply scoped, least‑privilege keys per
deployment (see [Deployment](deployment.md)).
