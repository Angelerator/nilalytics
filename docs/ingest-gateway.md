# Ingest gateway

The gateway is the **public front door** for browsers and mobile apps. It solves
the three things the internal OTLP server can't do safely on its own.

| Problem | How the gateway fixes it |
|---------|--------------------------|
| Browsers need **CORS** | Adds `Access-Control-Allow-*` headers + answers preflight |
| Endpoint must be **public + TLS** | Binds a configurable host; optional TLS cert/key |
| Clients must not ship a **long‑lived secret** | Issues **short‑lived** HMAC tokens; internal token stays on the host |

## Run it

```bash
nilalytics gateway
```

```
[nilalytics] gateway ready: http://127.0.0.1:4319
  mint:   POST /v1/token   (header 'x-ingest-key')
  ingest: POST /v1/logs|/v1/traces|/v1/metrics (Bearer short-lived token)
  forwards to internal http://127.0.0.1:4318
```

## Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/v1/token` | `x-ingest-key` | Mint a short‑lived token |
| POST | `/v1/logs` `/v1/traces` `/v1/metrics` | `Authorization: Bearer <token>` | Ingest OTLP (forwarded) |
| OPTIONS | any | – | CORS preflight (`204`) |
| GET | `/healthz` | – | Liveness |

## Token flow

```
app  ──POST /v1/token (x-ingest-key)──▶  gateway  ──▶  { token, expires_in: 900 }
app  ──POST /v1/logs (Bearer token)───▶  gateway  ──verify + forward with internal token──▶  OTLP server
```

- The **ingest key** (`NILA_INGEST_KEY`) is the only value a client ships. It
  can *only mint* short‑lived write tokens — it cannot read data. It is
  **rotatable** server‑side.
- **Short‑lived tokens** expire (`NILA_GATEWAY_TOKEN_TTL`, default 15 min), so a
  leaked token dies fast.
- The **internal ingest token never leaves the host**.

## Expose it

```bash
export NILA_GATEWAY_HOST=0.0.0.0        # accept real devices/browsers
export NILA_GATEWAY_CORS=https://app.example.com   # restrict origins in prod
```

## TLS

Terminate TLS at the gateway, or run it behind a reverse proxy.

```bash
export NILA_GATEWAY_CERT=/etc/tls/fullchain.pem
export NILA_GATEWAY_KEY=/etc/tls/privkey.pem
```

## Hardening

- Put `/v1/token` behind **your app's own user auth** for the strongest posture
  (mint tokens only for authenticated sessions).
- Rate‑limit `/v1/token` at your proxy.
- Rotate `NILA_INGEST_KEY` and `NILA_GATEWAY_SECRET` periodically.
