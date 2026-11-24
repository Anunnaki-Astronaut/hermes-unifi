# Changelog

## Unreleased

## 0.4.0 - 2026-11-22

- Added **Anunnaki** in both Light and Dark to Theme Maker. Apply either mode separately; Match Desktop stays the default, and existing palettes are kept.
- The theme changes appearance only. UniFi monitoring, credentials, and permissions are unchanged.

## 0.3.0 - 2026-11-20

- Connect an optional local UniFi console to see connected clients and check device health, Wi-Fi, ports, and WAN. Diagnostics explains what it found and what to check next. Hermes still cannot change the network.
- Use the dashboard gear to open native Settings. Follow the Desktop theme or system setting, choose light or dark, or customize a palette in Theme Maker. Preferences stay scoped to the Desktop connection and profile.
- Read the console over verified HTTPS or with a user-confirmed SHA-256 certificate pin. The setup guide shows how to copy the fingerprint in Firefox without accepting the browser warning. `UNIFI_NETWORK_API_KEY` is stored for the selected Hermes profile, not in the Desktop renderer.
- Ask Hermes about network health and connected clients with `unifi_status`, `unifi_diagnose`, `unifi_devices`, and `unifi_clients`. IP addresses are hidden by default. The plugin does not return the MAC address field or raw API identifiers.
- Follow Site Manager pagination and honor rate-limit cooldowns. Diagnostics flags partial console reads. Check ISP Health directly for Site Manager ISP feed errors, which Diagnostics can omit.

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
