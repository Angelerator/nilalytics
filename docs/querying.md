# Querying

Reads go through the **Quack** protocol: clients connect to the server and ship
SQL to it — they never touch object‑storage credentials. Reads are limited to a
read‑only policy (see [Security](security.md)).

## Built‑in views

```bash
nilalytics query report      # totals, funnel, errors, devices, identified persons, latency
nilalytics query traces      # recent spans + p95 latency per span
nilalytics query metrics     # metric names, counts, averages (e.g. web-vitals)
nilalytics query errors      # recent errors (type, message, service)
nilalytics query stitch      # cross-device identity graph
nilalytics query snapshots   # DuckLake snapshots
nilalytics query asof "5 minutes"   # time travel: state N ago vs now
nilalytics query changes             # change feed between snapshots
nilalytics query count       # total rows
nilalytics query schema      # otlp_logs columns
```

## Your own SQL over Quack

Any DuckDB client (including **DuckDB‑WASM** in a browser) can read the lake:

```sql
INSTALL quack FROM core_nightly; LOAD quack;
CREATE SECRET (TYPE quack, TOKEN '<NILA_QUACK_TOKEN>', SCOPE 'quack:localhost');
ATTACH 'quack:localhost' AS remote;

-- ship a query to the server (where the lake is attached)
FROM remote.query('
  SELECT body AS event, count(*) AS n
  FROM lake.main.otlp_logs
  GROUP BY 1 ORDER BY n DESC
');
```

!!! note "Read‑only"
    The server rejects destructive statements (`INSERT`, `UPDATE`, `DELETE`,
    `DROP`, `ALTER`, `ATTACH`, …) from Quack clients. Dashboards can read and run
    maintenance functions, but cannot mutate data.

## Backend activity

Backend spans land in `otlp_traces` (`status_code`: 1 = ok, 2 = error). Get
success/failure and p95 latency per route:

```sql
FROM remote.query('
  SELECT json_extract_string(span_attributes, ''$."http.route"'') AS route,
         count(*) AS calls,
         count(*) FILTER (WHERE status_code = 2) AS errors,
         round(quantile_cont(duration_time_unix_nano, 0.95) / 1e6) AS p95_ms
  FROM lake.main.otlp_traces
  GROUP BY 1 ORDER BY calls DESC
');
```

See [Backend activity](backend.md) for instrumenting and tying spans to the user.

## Handy columns

`otlp_logs`: `time_unix_nano`, `body` (event name), `severity_text`,
`service_name`, `log_attributes` (JSON with `event.name`, `user.id`,
`anonymous.id`, `session.id`, `page`, `exception.*`), and any promoted resource
columns (e.g. `resource_attr_deployment_environment`).

Extract JSON attributes with:

```sql
json_extract_string(log_attributes, '$."user.id"')
```

## Performance

- Recent events are **inlined in the catalog** → sub‑second.
- The table is **partitioned by day** and **sorted by event + time**, so filtered
  historical queries prune to a few files.
- For long‑range dashboards, keep a pre‑aggregated rollup table.

## Connect a BI tool / semantic layer

Because reads are plain SQL over DuckDB, you can point tools like
[stratif.io](https://stratif.io) (warehouse‑native product analytics on DuckDB)
at the same lake for funnels/retention UIs.
