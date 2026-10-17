# Contributing

Keep changes focused and explain the problem and resulting behavior. Run the full pytest suite, Node syntax checks, deterministic rendering and byte comparisons for all four previews, Plugin Doctor, and `git diff --check` before submitting. Commands are in [README.md](README.md#development-and-verification).

Use synthetic-only fixtures and screenshots. Do not include credentials, raw API responses, or real network details in code, tests, screenshots, issues, or logs. Keep public attribution impersonal and preserve the MIT attribution to Hermes UniFi contributors.

Preserve the read-only and fixed-origin contracts: only the three allowlisted GET paths under `https://api.ui.com/v1`, no configurable endpoint, and no arbitrary request surface. Preserve scoped secrets, verified TLS, bounded transport, sanitized output/errors, and rate-limit handling. Stable identifiers must remain suppressed; temporary row numbers are not identities and cannot correlate refreshes.

Future write controls or agent tools require separate design and security approval. They must not be introduced as incidental changes to this monitor. Use text-only UniFi branding, preserve the disclaimer, and do not add official or third-party logo artwork.

Report vulnerabilities privately through GitHub's private vulnerability reporting, not public issues. See [SECURITY.md](SECURITY.md) and [PRIVACY.md](PRIVACY.md).
