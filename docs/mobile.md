# Mobile (OpenTelemetry)

Native mobile apps send to nilalytics using an **OpenTelemetry SDK** (Grafana
Faro is web‑only). Because the ingest is standard OTLP, any OTel exporter works.

Mobile is actually **simpler than the browser**: there is no CORS to configure.

## SDKs

| Platform | SDK |
|----------|-----|
| iOS / Swift | [OpenTelemetry‑Swift](https://github.com/open-telemetry/opentelemetry-swift) (or Embrace) |
| Android / Kotlin | [OpenTelemetry Android](https://github.com/open-telemetry/opentelemetry-android) / Kotlin Multiplatform (or Embrace) |
| React Native / Flutter | their OpenTelemetry SDKs |
| anything | a plain HTTPS `POST` of OTLP JSON |

## The flow

1. Fetch a short‑lived token from the gateway `POST /v1/token` (header `x-ingest-key`).
2. Configure an OTLP/HTTP exporter → the gateway, with `Authorization: Bearer <token>`.
3. Emit events/errors/spans. Re‑mint the token before it expires.

### iOS (Swift, sketch)

```swift
// 1) mint a short-lived token
var req = URLRequest(url: URL(string: "https://ingest.example.com/v1/token")!)
req.httpMethod = "POST"
req.setValue(ingestKey, forHTTPHeaderField: "x-ingest-key")
let (data, _) = try await URLSession.shared.data(for: req)
let token = (try JSONSerialization.jsonObject(with: data) as! [String: Any])["token"] as! String

// 2) configure the OTLP exporter to the gateway
let exporter = OtlpHttpLogExporter(
  endpoint: URL(string: "https://ingest.example.com/v1/logs")!,
  config: OtlpConfiguration(headers: [("Authorization", "Bearer \(token)")])
)
// register exporter with the OpenTelemetry LoggerProvider, then emit events/errors.
```

### Android (Kotlin, sketch)

```kotlin
// 1) mint token (x-ingest-key) -> token   ... (use your HTTP client)

// 2) OTLP exporter to the gateway
val exporter = OtlpHttpLogRecordExporter.builder()
    .setEndpoint("https://ingest.example.com/v1/logs")
    .addHeader("Authorization", "Bearer $token")
    .build()
// wire into the OpenTelemetry SdkLoggerProvider, then emit events/errors/spans.
```

## Map onto the identity model

Set the same attributes web uses, so a person stitches across phone + web:

- `anonymous.id` — a random UUID stored in **Keychain** (iOS) / **SharedPreferences** (Android).
- `session.id` — per app session.
- `user.id` — set on login, **hashed client‑side** (never send the raw email/id).

See [Identity & cross‑device](identity.md).

## What to send

| You capture | Send as | Lands in |
|-------------|---------|----------|
| product events | OTLP log with `event.name` | `otlp_logs` |
| crashes / errors | OTLP log, severity `ERROR`, `exception.*` | `otlp_logs` |
| screen load / network timing | OTLP span | `otlp_traces` |
| counters / vitals | OTLP metric | `otlp_metrics_*` |
