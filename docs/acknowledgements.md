# Acknowledgements

nilalytics is a thin layer over remarkable open‑source work. It is standing on
the shoulders of giants — deep thanks to everyone who built and maintains the
projects below. 🙏

## Built on

- **[DuckDB](https://duckdb.org/)** — the in‑process analytical engine at the core, by **DuckDB Labs** and the **DuckDB Foundation**.
- **[DuckLake](https://ducklake.select/)** — the SQL‑native lakehouse format (catalog + Parquet) that stores every event. Its **data inlining** is what makes streaming ingestion cheap and fast.
- **Quack** — DuckDB's client–server protocol, which serves the catalog to readers and to DuckDB‑WASM in the browser.
- **[duckdb‑otlp](https://github.com/smithclay/duckdb-otlp)** by **[@smithclay](https://github.com/smithclay)** — the embedded OTLP ingest server that lands telemetry straight into DuckLake, and does post‑seal compaction.
- **[OpenTelemetry](https://opentelemetry.io/)** (CNCF) — the vendor‑neutral standard every nilalytics client speaks.
- **[Grafana Faro](https://github.com/grafana/faro-web-sdk)** by **Grafana Labs** — the web RUM SDK and its OTLP transport.
- **DuckDB `httpfs` / `azure` extensions** — object‑storage access across S3, GCS, R2, and Azure / ADLS.
- **[MinIO](https://min.io/)** — S3‑compatible object storage used for local development.

## Inspiration

nilalytics wouldn't exist without prior art that proved the shape of this idea:

- **[canardstack](https://github.com/smithclay/canardstack)** by [@smithclay](https://github.com/smithclay) — querying OpenTelemetry data stored in DuckLake with a Quack catalog.
- **[icelight](https://github.com/cliftonc/icelight)** by [@cliftonc](https://github.com/cliftonc) — first‑party analytics.js → Iceberg on R2 → DuckDB.
- **[stratif.io](https://stratif.io/)** by **Carlo Abi Chahine** — open‑source, warehouse‑native product analytics on DuckDB.
- **[Definite](https://www.definite.app/blog/duckdb-quack-ducklake-catalog)** — for the clear writeup on using DuckDB + Quack as the DuckLake catalog.

## Dependencies

### Runtime (Python)

| Package | License | Used for |
|---------|---------|----------|
| [duckdb](https://pypi.org/project/duckdb/) | MIT | engine + all extensions |
| [requests](https://pypi.org/project/requests/) | Apache‑2.0 | HTTP (emitter, gateway forwarding) |
| [pytz](https://pypi.org/project/pytz/) | MIT | timezone support for time‑travel queries |

### DuckDB extensions (auto‑installed at runtime)

`ducklake` · `quack` · `otlp` · `httpfs` · `azure`

### Documentation

- [MkDocs](https://www.mkdocs.org/) and [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/) by **[@squidfunk](https://github.com/squidfunk)** (Martin Donath).

## Licensing

nilalytics is released under [Apache‑2.0](https://github.com/Angelerator/nilalytics/blob/main/LICENSE). Every
dependency and referenced project is distributed under its own license — please
review each one for your use case.
