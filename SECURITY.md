# Security

## Report a vulnerability privately

Use GitHub's private vulnerability reporting from the repository's **Security → Report a vulnerability** page. Do not report vulnerabilities in public issues. If that option is unavailable, do not post sensitive details publicly; private reporting must be enabled before accepting reports there.

Include the affected plugin/Hermes versions, a concise impact description, reproduction steps using synthetic data, and relevant sanitized error codes. Exclude credentials, upstream response bodies, real identifiers, and screenshots or logs containing private infrastructure details.

## Read-only request boundaries

The plugin is read-only. All upstream calls are backend GET requests to the fixed Site Manager origin. The endpoint allowlist contains only sites, devices, and 5-minute ISP metrics. TLS uses `ssl.create_default_context()` with hostname and certificate validation. Environment proxies and redirect forwarding are disabled. There is no configurable transport, URL, path, headers, method, custom CA, or TLS bypass.

## Credential handling

Secrets are obtained with `agent.secret_scope.get_secret`. Lookup failures, including unscoped access, fail closed. Environment lookup is allowed only when that module is absent for standalone development. Plugin settings are never read for credentials. Keys are sent only as `X-API-KEY`, are not logged, and are filtered from projected text. No real secrets are used by tests or previews.

The API key is never exposed to Desktop JavaScript. Configure it through Hermes' masked secret field for the selected profile. Never paste it into chat, URLs, JavaScript, screenshots, issues, or Git.

## Bounded transport and safe errors

Requests default to 10 seconds and accept only 1..30 seconds internally; routes accept no arguments. Reads are capped at 5 MiB plus one overflow sentinel byte. Errors never expose upstream bodies, trace IDs, URLs, or raw exception messages. 401/403 map to authentication_failed, 429 to rate_limited, other HTTP failures to upstream_http_error, transport failures to unifi_unreachable, and invalid payloads to invalid_upstream_response. Retry-After accepts integer or decimal seconds, conservatively ceiling-rounded and capped at one day; backend process-local cooldown prevents further calls during that period. Restarting the backend clears this transient cooldown. No controller payload is persisted.

## Renderer and privacy boundaries

Renderer projections allow only documented display fields and aggregate metrics. Unknown fields are discarded. Free-text labels containing known identifiers, MAC/IP patterns, or the credential are suppressed. ISP history is reduced to one latest period per site/host. Preview generation has no network primitives and embeds a restrictive content security policy.

Site / host numbers are temporary and may change after refresh. They are presentation-only row numbers, not device/site/host identities, and must not be used to correlate data across refreshes. Stable identifiers are deliberately suppressed.

There is no arbitrary request surface, mutation, or agent tool. See [PRIVACY.md](PRIVACY.md) for data handling and sharing precautions.
