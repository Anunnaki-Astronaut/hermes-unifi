# Contributing

Keep changes focused and explain the problem and resulting behavior. Run the full pytest suite, Node syntax checks, deterministic rendering and byte comparisons for all six previews, Plugin Doctor, and `git diff --check` before submitting. Commands are in [README.md](README.md#development-and-verification).

Use synthetic-only fixtures and screenshots. Do not include credentials, raw API responses, or real network details in code, tests, screenshots, issues, or logs. Keep public attribution impersonal and preserve the MIT attribution to Hermes UniFi contributors.

Preserve the read-only and fixed-origin contracts: only the three allowlisted GET paths under `https://api.ui.com/v1`, only the documented GET paths under the console's `/proxy/network/integration/v1`, a console host restricted to private LAN addresses and local hostnames, no other configurable endpoint, and no arbitrary request surface. Preserve scoped secrets, verified or pinned TLS (never disabled), bounded transport, sanitized output/errors, and rate-limit handling. Stable identifiers and MAC addresses must remain suppressed; temporary row numbers and handles are not identities and cannot correlate refreshes.

Agent tools must stay read-only, accept only bounded enum or short-text inputs, never raise, and never return credentials, URLs, MAC addresses, or raw identifiers. Diagnostic rules must be deterministic, covered by synthetic tests, and written in plain English with a recommendation.

Future write controls or agent tools that change the network require separate design and security approval, a dry-run preview, explicit in-chat confirmation, and before/after snapshots. They must not be introduced as incidental changes. Use text-only UniFi branding, preserve the disclaimer, and do not add official or third-party logo artwork.

Report vulnerabilities privately through GitHub's private vulnerability reporting, not public issues. See [SECURITY.md](SECURITY.md) and [PRIVACY.md](PRIVACY.md).
