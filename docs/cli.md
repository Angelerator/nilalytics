# CLI reference

All commands are subcommands of `nilalytics`. Each is also runnable as
`python -m nilalytics.<module>`.

```bash
nilalytics <command> [args]
```

## `server`

Runs the OTLP ingest server (`:4318`) and the Quack catalog server (`:9494`),
attaching the DuckLake. Blocks until interrupted (Ctrl‑C commits buffered rows).

```bash
nilalytics server
```

## `gateway`

Runs the public ingest gateway (`:4319`) — CORS, short‑lived tokens, optional TLS
— forwarding to the internal OTLP server. See [Ingest gateway](ingest-gateway.md).

```bash
nilalytics gateway
```

## `emit`

Sends sample telemetry (useful for demos and load checks).

```bash
nilalytics emit [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `-n`, `--count` | `200` | Number of log events |
| `-b`, `--batch-size` | `50` | Events per POST |
| `-e`, `--error-rate` | `0.1` | Fraction that are errors |
| `--traces` | `10` | Trace spans |
| `--metrics` | `10` | Metric points |
| `--persons` | `0` | Simulate N cross‑device people (2 devices each, identified) |

## `query`

Reads over Quack. Default subcommand is `report`.

```bash
nilalytics query [subcommand] [args]
```

| Subcommand | Description |
|------------|-------------|
| `report` | Totals, funnel, errors, devices, identified persons, latency |
| `traces` | Recent spans + p95 latency per span |
| `metrics` | Metric names, counts, averages |
| `errors` | Recent errors |
| `stitch` | Cross‑device identity graph |
| `snapshots` | DuckLake snapshots |
| `asof <interval>` | Time travel (e.g. `asof "5 minutes"`) |
| `changes [start] [end]` | Change feed between snapshots |
| `count` | Total rows |
| `schema` | `otlp_logs` columns |
| `sample` | One raw row |

## `maintenance`

Flush inlined data to Parquet and compact. See [Maintenance](maintenance.md).

```bash
nilalytics maintenance [--expire]
```

| Option | Description |
|--------|-------------|
| `--expire` | Also expire old snapshots + delete unused files (destructive) |
