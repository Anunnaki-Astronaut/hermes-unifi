# Privacy

Hermes UniFi is a read-only monitor. The backend reads sites, devices, and the latest 5-minute ISP metrics from the official Site Manager API. Only fixed GET requests to `https://api.ui.com/v1/sites`, `/v1/devices`, and `/v1/isp-metrics/5m` are allowed. There is no configurable endpoint.

## What reaches Desktop

The renderer receives selected display fields and aggregate metrics. Clients and client counts, MAC/IP addresses, stable identifiers, trace IDs, history, and arbitrary fields are excluded. ISP history is reduced to the latest timestamped period per site/host pair.

Sensitive free-text values containing known identifiers, MAC/IP patterns, or the API key are suppressed. This filtering does not make all remaining names or descriptions safe to publish. Review and scrub screenshots, issues, and logs; never share raw API responses or private infrastructure details.

Site / host numbers are temporary and may change after refresh. They are presentation-only row numbers, not device/site/host identities. They must not be used to correlate data across refreshes. Stable identifiers are deliberately suppressed.

Undefined units remain unlabeled rather than guessed, including latency, downtime, uptime, and packet loss.

## Storage and services

The plugin has no controller-data persistence, telemetry, analytics, exports, or third-party services beyond the official API. Responses are processed in memory; the backend keeps a transient rate-limit cooldown, and Desktop holds view data for display. The API key is stored separately by Hermes in the selected profile's credential store.

## API key handling

Backend credential access uses `agent.secret_scope.get_secret` for `UNIFI_API_KEY` and fails closed on lookup errors. An environment fallback exists only when that module is absent for standalone development. Ordinary plugin settings are not a credential source.

The key is sent only in the backend `X-API-KEY` header to the fixed official origin. It is not logged or exposed to Desktop JavaScript. Enter it only in the masked secret field; never paste it into chat, URLs, JS, screenshots, issues, or Git. Store it securely and revoke it through Site Manager if exposed or no longer needed.

See [SECURITY.md](SECURITY.md) for transport controls and private vulnerability reporting.
