# Security

nilalytics is token‑authenticated and read‑restricted by default.

## Ingest authentication

The OTLP server requires a Bearer token (`NILA_OTLP_TOKEN`). Unauthenticated
writes are rejected (`401`). In production, clients never hold this token — they
go through the [gateway](ingest-gateway.md) with short‑lived tokens.

## Short‑lived client tokens

The gateway issues HMAC‑signed tokens that expire (default 15 min). The value a
client ships is the **ingest key**, which can only *mint* write tokens (not read
data) and is rotatable. The internal ingest token never leaves the host.

## Read‑only query authorization

Quack clients (dashboards, DuckDB‑WASM) are restricted by a server‑side policy
that **blocks destructive statements** — `INSERT`, `UPDATE`, `DELETE`, `DROP`,
`ALTER`, `CREATE`, `ATTACH`, `DETACH`, `COPY`, `TRUNCATE`, `INSTALL`, `LOAD`.
Reads and maintenance functions are allowed; data cannot be tampered with or
exfiltrated by attaching external databases.

!!! note
    This is a defense‑in‑depth guard on top of the Quack token. For strict
    multi‑tenant isolation, use per‑tenant tokens/prefixes (roadmap).

## Startup guard

For a **remote** S3 endpoint, the server refuses to start if TLS is off or the
default `minioadmin` credentials are used. GCS/R2/Azure are validated for
required credentials.

## Secrets at rest

Generated tokens/salt/keys are stored in `<data dir>/.nila_secrets.json` with
mode `0600` (owner‑only), inside a directory that is git‑ignored. Set them
explicitly via env in production and rotate them yourself.

## Object‑storage credentials

The server holds the storage credentials so clients don't. Use **scoped,
least‑privilege** keys per deployment (write‑limited to your prefix). For S3, you
can supply short‑lived STS credentials via `NILA_S3_SESSION_TOKEN`.

## Privacy / PII

- `user.id` is a **salted hash** computed client‑side — the lake can't reverse it
  to a real identity. See [Identity](identity.md).
- No fingerprinting.
- Error stacktraces and event attributes are stored as sent — mask sensitive
  fields client‑side and add a consent flag to honor opt‑outs.

## Transport

- Terminate **TLS** at the gateway (cert/key) or a reverse proxy.
- Keep the internal OTLP server and Quack catalog bound to **localhost**; expose
  only the gateway.
