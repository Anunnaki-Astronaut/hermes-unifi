# Changelog

## Unreleased

- Replace the handmade brand mark with a bold UniFi text heading and clarify unofficial affiliation in the footer, documentation, and descriptions.
- Apply Hermes-backed good, warning, bad, and muted semantic tones while preserving neutral unknown states and warning-only firmware availability.
- Expand semantic and branding regression coverage and regenerate all four deterministic previews.

- Refine the read-only dashboard with clear navigation, compact health summaries, status pills, attention rows, scrollable tables, and data notes.
- Format display enums and blanks without changing source data; preserve unit-free uptime and ISP metrics.
- Verify all four deterministic HTML previews and synthetic display states in tests and CI.

## 0.1.0

- Initial read-only native Hermes UniFi plugin, disabled by default.
- Overview, Sites, Devices, and latest-period ISP Health through fixed Site Manager GET endpoints.
- Scoped credentials, verified TLS, bounded transport, sanitized projections/errors, and rate-limit cooldown.
- Synthetic tests, static preview renderer, CI checks, and root Hermes registration.
