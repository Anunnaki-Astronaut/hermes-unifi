# Security

All upstream calls are backend GET requests to the fixed Site Manager origin. The endpoint allowlist contains only sites, devices, and 5-minute ISP metrics. TLS uses `ssl.create_default_context()` with hostname and certificate validation. Environment proxies and redirect forwarding are disabled. There is no configurable transport, URL, path, headers, method, custom CA, or TLS bypass.

Secrets are obtained with `agent.secret_scope.get_secret`. Lookup failures, including unscoped access, fail closed. Environment lookup is allowed only when that module is absent for standalone development. Plugin settings are never read for credentials. Keys are sent only as `X-API-KEY`, are not logged, and are filtered from projected text. No real secrets are used by tests or previews.

Requests default to 10 seconds and accept only 1..30 seconds internally; routes accept no arguments. Reads are capped at 5 MiB plus one overflow sentinel byte. Errors never expose upstream bodies, trace IDs, URLs, or raw exception messages. 401/403 map to authentication_failed, 429 to rate_limited, other HTTP failures to upstream_http_error, transport failures to unifi_unreachable, and invalid payloads to invalid_upstream_response. Retry-After accepts integer or decimal seconds, conservatively ceiling-rounded and capped at one day; backend process-local cooldown prevents further calls during that period. Restarting the backend clears this transient cooldown. No controller payload is persisted.

Renderer projections allow only documented display fields and aggregate metrics. Unknown fields are discarded. Free-text labels containing known identifiers, MAC/IP patterns, or the credential are suppressed. ISP history is reduced to one latest period per site/host. Preview generation has no network primitives and embeds a restrictive content security policy.

Report vulnerabilities privately to the repository maintainer. Do not include credentials, upstream response bodies, real identifiers, or screenshots containing private infrastructure details.
