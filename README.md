# nilalytics

[![PyPI](https://img.shields.io/pypi/v/nilalytics)](https://pypi.org/project/nilalytics/)
[![Python](https://img.shields.io/pypi/pyversions/nilalytics)](https://pypi.org/project/nilalytics/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-angelerator.github.io-14b8a6)](https://angelerator.github.io/nilalytics/)

**The batteries‑included, OpenTelemetry‑native way to run your own web & mobile product analytics — on a DuckLake in your object storage.**

nilalytics collects product events, errors, and performance data over
[OpenTelemetry](https://opentelemetry.io/) (OTLP), stores them in a
[DuckLake](https://ducklake.select/) lakehouse on any major cloud's object
storage, and serves sub‑second reads over DuckDB's [Quack](https://duckdb.org/docs/stable/core_extensions/quack) protocol — no warehouse, no per‑event fees, no data leaving your infrastructure.

- **Web, mobile _and_ backends:** Grafana Faro (web), OpenTelemetry SDKs (mobile + server) → OTLP. Record user actions *and* whether the backend calls behind them succeeded — in one lake.
- **Runs on any cloud:** S3, MinIO, Google Cloud Storage, Cloudflare R2, or Azure / ADLS Gen2.
- **Recommendation‑ready:** a curated per‑user `user_events` table, partitioned **subject › date › person**, so "everything this user did" is one fast read. Look anyone up by email / account id / phone.
- **Subjects & AI usage:** every event is classified — `errors` · `activities` · `ai_usage` · `traceability` — so category reads and LLM/token tracking prune to their own partition.
- **Small files solved:** DuckLake data inlining + compaction keep streaming writes fast and files healthy.
- **Bounded storage:** opt‑in data retention drops old events (with a read‑only dry‑run preview).
- **Batteries included:** funnels, retention, errors, traces, metrics, cross‑device identity.
- **Secure by default:** token‑authenticated ingest, read‑only query authz, a hardened public gateway.

📖 **Full documentation:** <https://angelerator.github.io/nilalytics/>

## Install

```bash
pip install nilalytics
```

> Also works with `pipx install nilalytics` or `uv tool install nilalytics`.
> Bleeding edge from source: `pip install git+https://github.com/Angelerator/nilalytics`.

## 60‑second local demo

```bash
# 1. object storage (local MinIO)
minio server .minio-data --address 127.0.0.1:9100 --console-address 127.0.0.1:9101 &
mc alias set nila http://127.0.0.1:9100 minioadmin minioadmin
mc mb --ignore-existing nila/nilalytics

# 2. run the pipeline
nilalytics server &      # ingest + Quack catalog
nilalytics gateway &     # public ingest gateway (CORS + tokens)

# 3. send + query
nilalytics emit --count 200 --persons 5
nilalytics query report
nilalytics query subject ai_usage 7                # per-subject read (last 7 days)
nilalytics query user --key person0@example.com 3  # one person's activity (last 3 days)
```

## Architecture

```mermaid
flowchart LR
  W["Web · Grafana Faro"] -->|OTLP + token| GW
  M["Mobile · OpenTelemetry"] -->|OTLP + token| GW
  GW["Ingest Gateway<br/>CORS · tokens · TLS"] --> SRV["OTLP server<br/>(duckdb-otlp)"]
  B["Backend services · OpenTelemetry"] -->|"OTLP · private net"| SRV
  SRV --> LAKE[("DuckLake<br/>DuckDB + Quack catalog<br/>+ Parquet on object storage")]
  LAKE --> READ["Reads: DuckDB / DuckDB-WASM<br/>over Quack"]
```

## Acknowledgements

nilalytics stands on the shoulders of giants. Huge thanks to
[DuckDB](https://duckdb.org/), [DuckLake](https://ducklake.select/) and Quack (DuckDB Labs / DuckDB Foundation),
[duckdb‑otlp](https://github.com/smithclay/duckdb-otlp) ([@smithclay](https://github.com/smithclay)),
[OpenTelemetry](https://opentelemetry.io/) (CNCF),
[Grafana Faro](https://github.com/grafana/faro-web-sdk) (Grafana Labs),
and [MinIO](https://min.io/) — plus the projects that inspired it:
[canardstack](https://github.com/smithclay/canardstack),
[icelight](https://github.com/cliftonc/icelight), and
[stratif.io](https://stratif.io/).

Full credits and dependency list: [Acknowledgements](https://angelerator.github.io/nilalytics/acknowledgements/).

## License

[Apache‑2.0](LICENSE) © Angelerator

