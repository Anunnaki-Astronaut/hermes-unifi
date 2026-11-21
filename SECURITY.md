# Security

## Report a vulnerability privately

Use GitHub's private vulnerability reporting from the repository's **Security → Report a vulnerability** page. Do not report vulnerabilities in public issues. If that option is unavailable, do not post sensitive details publicly; private reporting must be enabled before accepting reports there.

Include the affected plugin/Hermes versions, a concise impact description, reproduction steps using synthetic data, and relevant sanitized error codes. Exclude credentials, upstream response bodies, real identifiers, and screenshots or logs containing private infrastructure details.

## Read-only request boundaries

The plugin is read-only. All upstream calls are backend GET requests. Cloud calls go to the fixed Site Manager origin with an allowlist of sites, devices, and 5-minute ISP metrics. Console calls go to `https://<console-host>/proxy/network/integration/v1` with a fixed set of documented read paths (`/info`, `/sites`, per-site devices, device details, latest device statistics, clients, WANs, networks, Wi-Fi broadcasts). The console host is validated before use: it must be an RFC 1918 or link-local IPv4 address, a unique-local or link-local IPv6 address, a bare hostname, or a hostname ending in `.local`, `.lan`, `.home`, `.internal`, or `.home.arpa`; scheme, path, query, credentials, loopback, multicast, and public addresses are rejected. Agent tools accept only a focus enum and an 80-character search word. There is no configurable transport, URL, path, headers, method, custom CA, or TLS bypass.

## Console TLS

Cloud TLS uses `ssl.create_default_context()` with hostname and certificate validation. Console TLS uses the same default context unless a certificate pin is configured. With a pin, the CA and hostname checks are replaced (not skipped) by a SHA-256 comparison of the presented leaf certificate against the user-confirmed fingerprint; a mismatch closes the connection before any request or header is sent and fails closed with `certificate_mismatch`. The fingerprint helper performs an unverified handshake only to read the certificate for the user to confirm against the console UI; it sends no request and no credential. Environment proxies and redirect forwarding are disabled for both sources.

## Credential handling

Secrets are obtained with `agent.secret_scope.get_secret` (`UNIFI_API_KEY`, `UNIFI_NETWORK_API_KEY`). Lookup failures, including unscoped access, fail closed. Environment lookup is allowed only when that module is absent for standalone development. Plugin settings are never read for credentials. Keys are sent only as `X-API-KEY`, are not logged, are filtered from projected text, and never appear in Desktop JavaScript or agent tool output. No real secrets are used by tests or previews.

## Bounded transport and safe errors

Requests default to 10 seconds and accept only 1..30 seconds internally; routes accept no arguments. Reads are capped at 5 MiB plus one overflow sentinel byte per response. Sites and devices follow only upstream-provided continuation tokens, with at most 10 pages and 20 MiB of complete responses per view; the final overflow probe can consume one byte beyond the remaining budget. Console lists use offset pagination in pages of 200, at most 10 pages per list, and device details and statistics are read for at most 60 devices per snapshot. Errors never expose upstream bodies, trace IDs, URLs, or raw exception messages. 401/403 map to authentication_failed, 429 to rate_limited, other HTTP failures to upstream_http_error, transport failures to unifi_unreachable or console_unreachable, TLS trust failures to certificate_untrusted or certificate_mismatch, and invalid payloads to invalid_upstream_response. Retry-After accepts integer or decimal seconds (up to 18 fractional digits), conservatively ceiling-rounded and capped at one day. A missing or invalid header falls back to a 60-second cooldown; backend process-local cooldown prevents further calls during that period. Restarting the backend clears this transient cooldown. No controller payload is persisted beyond a 30-second in-memory snapshot.

## Renderer, tool and privacy boundaries

Projections allow only documented display fields, aggregate metrics, and findings. Unknown fields are discarded. MAC addresses are always removed; IP addresses are removed unless the user enables them; free text containing MAC/IP patterns or a credential is redacted or suppressed. Upstream identifiers are replaced by temporary per-process handles. ISP history is reduced to one latest period per site/host. Agent tool handlers never raise, return JSON only, and map every failure to a safe code. Preview generation has no network primitives and embeds a restrictive content security policy.

Site / host numbers and device/client handles are temporary and may change after refresh. They are presentation-only row numbers, not device/site/host identities, and must not be used to correlate data across refreshes. Stable identifiers are deliberately suppressed.

There is no arbitrary request surface and no mutation. Agent tools are read-only. Diagnostics may describe a fix (restart a device, power-cycle a port) but mark it unavailable; a future write capability requires separate design and security approval, a dry-run preview, explicit in-chat confirmation, and before/after snapshots. See [PRIVACY.md](PRIVACY.md) for data handling and sharing precautions.
