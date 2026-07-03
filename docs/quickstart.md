# Quickstart

Run the whole pipeline locally in a couple of minutes. Assumes you've done
[Install](install.md) and have MinIO running with a `nilalytics` bucket.

## 1. Start the server and gateway

```bash
nilalytics server &     # OTLP ingest (:4318) + Quack catalog (:9494)
nilalytics gateway &    # public ingest gateway (:4319) with CORS + tokens
```

You should see `READY` and `GATEWAY READY` banners.

## 2. Send some events

```bash
# 200 product events + errors, plus 5 cross-device "people"
nilalytics emit --count 200 --persons 5 --traces 20 --metrics 20
```

## 3. Query it

```bash
nilalytics query report
```

```
total events: 250
by event:
  signup_complete   ...
  page_view         ...
  exception         ...
distinct devices:   ...
identified persons: ...
signup funnel:      ... start -> ... complete
aggregate query latency: 2.8 ms  [SUB-SECOND]
```

More views:

```bash
nilalytics query traces     # p95 latency per span
nilalytics query metrics    # web-vitals gauges
nilalytics query stitch     # people unified across devices
nilalytics query asof "5 minutes"   # time travel
nilalytics query changes    # change feed (activation source)
```

## 4. Compact when you like

```bash
nilalytics maintenance          # flush inlined rows -> Parquet + merge
```

## 5. Send events from a real app

- **Web:** wire up [Grafana Faro](web.md) to the gateway.
- **Mobile:** wire up an [OpenTelemetry SDK](mobile.md) to the gateway.

Both fetch a short‑lived token from the gateway and post OTLP — the same data you
just queried.

## Point it at a real cloud

Switch object storage with environment variables (see [Storage backends](storage-backends.md)):

```bash
# example: Cloudflare R2
export NILA_STORAGE=r2
export NILA_R2_ACCOUNT_ID=... NILA_R2_KEY=... NILA_R2_SECRET=...
export NILA_BUCKET=my-bucket
nilalytics server
```
