# Changelog

## 0.1.0 - 2026-10-16

First public release.

- Add a read-only native Hermes UniFi monitor, disabled by default, with Overview, Sites, Devices, and latest-period ISP Health.
- Restrict upstream access to fixed-origin Site Manager GET endpoints; provide no mutations or agent tools.
- Use scoped credentials, verified TLS, bounded transport, sanitized projections and errors, and a rate-limit cooldown.
- Use text-only UniFi branding and an explicit unofficial-affiliation disclaimer.
- Add navigation, compact health summaries, status pills, attention rows, scrollable tables, and data notes.
- Apply Hermes semantic status colors for good, warning, bad, and muted states; keep unknown states neutral and firmware availability at warning level.
- Format display enums and blanks without changing source data; leave undefined uptime and ISP metric units unlabeled.
- Clarify that temporary site/host numbers may change after refresh and cannot identify or correlate records.
- Include synthetic fixtures, four deterministic HTML previews, semantic and branding regression tests, CI checks, and root Hermes registration.
- Document installation, API-key setup, current limits, privacy, security reporting, and contribution requirements; reference synthetic public PNG previews for release preparation.
- Add a pinned secret-scan workflow with provider verification disabled.
