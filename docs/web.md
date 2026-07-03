# Web (Grafana Faro)

Instrument a website with [Grafana Faro](https://github.com/grafana/faro-web-sdk)
and send everything — errors, web‑vitals, traces, and custom events — to
nilalytics as OTLP. Faro is built on OpenTelemetry, so it's the web flavour of
the same standard the mobile SDKs use.

!!! tip "One SDK, not two"
    You do **not** need Faro *and* raw OpenTelemetry‑JS. Faro already includes OTel
    tracing plus error/web‑vitals autocapture.

## 1. Install

```bash
npm install @grafana/faro-web-sdk @grafana/faro-web-tracing @grafana/faro-transport-otlp-http
```

## 2. Fetch a short‑lived token, then initialize Faro

The browser never holds a long‑lived secret. It presents a public **ingest key**
to the gateway's `/v1/token` endpoint and gets back a short‑lived token.

```js
import { initializeFaro, getWebInstrumentations } from '@grafana/faro-web-sdk';
import { TracingInstrumentation } from '@grafana/faro-web-tracing';
import { OtlpHttpTransport } from '@grafana/faro-transport-otlp-http';

const GATEWAY = 'https://ingest.example.com';       // your nilalytics gateway
const INGEST_KEY = '<public ingest key>';            // rotatable, mint-only

async function mintToken() {
  const r = await fetch(`${GATEWAY}/v1/token`, {
    method: 'POST',
    headers: { 'x-ingest-key': INGEST_KEY },
  });
  const { token } = await r.json();
  return token;
}

const token = await mintToken();

const faro = initializeFaro({
  app: { name: 'my-web', version: '1.0.0' },
  instrumentations: [...getWebInstrumentations(), new TracingInstrumentation()],
  transports: [
    new OtlpHttpTransport({
      logsURL:   `${GATEWAY}/v1/logs`,
      tracesURL: `${GATEWAY}/v1/traces`,
      requestOptions: { headers: { Authorization: `Bearer ${token}` } },
    }),
  ],
});
```

!!! note "Refresh the token"
    Tokens expire (default 15 min). Re‑mint on a timer, or when a request returns
    `401`, and update the transport headers.

## 3. Map onto the identity model

```js
faro.api.setSession({ id: sessionId });        // -> session.id
faro.api.setUser({ id: await hashKey(email) }); // -> user.id (hash client-side)
// anonymous.id: persist a random UUID and set it as a global attribute / user meta
```

This enables [cross‑device stitching](identity.md) between web and mobile.

## What you get automatically

Faro captures, with no extra code:

- **Errors** — unhandled exceptions and rejections → `otlp_logs` (severity `ERROR`).
- **Web‑vitals** — LCP, INP, CLS, etc. → `otlp_metrics_*`.
- **Traces** — fetch/XHR timings → `otlp_traces`.
- **Custom events** — `faro.api.pushEvent('checkout_started', {...})` → `otlp_logs`.

## CORS

The gateway sets the CORS headers browsers require and answers preflight, so a
cross‑origin `POST` from your site works. Restrict the allowed origin in
production with `NILA_GATEWAY_CORS` (see [Ingest gateway](ingest-gateway.md)).
