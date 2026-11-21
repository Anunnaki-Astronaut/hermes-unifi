# Privacy

Hermes UniFi is a read-only monitor and diagnostics assistant. The backend reads sites, devices, and the latest 5-minute ISP metrics from the official Site Manager API, and, when configured, devices, device statistics, clients, WANs, networks, and Wi-Fi broadcasts from the official Network API on your local console. Only fixed GET requests are allowed: `https://api.ui.com/v1/sites`, `/v1/devices`, `/v1/isp-metrics/5m`, and the documented read paths under `https://<console-host>/proxy/network/integration/v1`. The console host is the only configurable destination and must be a private LAN address or local hostname.

## What reaches Desktop and the agent

The renderer and the agent tools receive selected display fields, aggregate metrics, and plain-English findings. MAC addresses, stable identifiers, trace IDs, history, and arbitrary fields are excluded. IP addresses are excluded unless **Show IP addresses** is enabled. Clients are included only from the local console and only as name, connection type, uplink, access type, authorization, and connection time. ISP history is reduced to the latest timestamped period per site/host pair.

Sensitive free-text values containing MAC/IP patterns or either API key are suppressed or redacted. This filtering does not make all remaining names or descriptions safe to publish. Review and scrub screenshots, issues, and logs; never share raw API responses or private infrastructure details.

Site / host numbers and device/client handles (`device-2`, `client-5`) are temporary and may change after refresh or backend restart. They are presentation-only row numbers, not device/site/host identities. They must not be used to correlate data across refreshes. Stable identifiers are deliberately suppressed.

Undefined units remain unlabeled rather than guessed, including latency, downtime, uptime, and packet loss.

## Storage and services

The plugin has no controller-data persistence, telemetry, analytics, exports, or third-party services beyond the official APIs. Responses are processed in memory; the backend keeps a transient rate-limit cooldown and a 30-second in-memory console snapshot so one read serves several views, and Desktop holds view data for display. API keys are stored separately by Hermes in the selected profile's credential store.

## API key handling

Backend credential access uses `agent.secret_scope.get_secret` for `UNIFI_API_KEY` (Site Manager) and `UNIFI_NETWORK_API_KEY` (console) and fails closed on lookup errors. An environment fallback exists only when that module is absent for standalone development. Ordinary plugin settings are not a credential source.

Each key is sent only in the backend `X-API-KEY` header to its fixed destination. Keys are not logged, not exposed to Desktop JavaScript, and not present in agent tool output. Enter them only in the masked secret fields; never paste them into chat, URLs, JS, screenshots, issues, or Git. Store them securely and revoke them (Site Manager, or the console's Integrations page) if exposed or no longer needed.

See [SECURITY.md](SECURITY.md) for transport controls and private vulnerability reporting.
