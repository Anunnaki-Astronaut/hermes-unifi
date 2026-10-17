# Hermes UniFi 0.1.0

Unofficial integration for read-only monitoring using the official UniFi Site Manager API. Requires Hermes >=0.22.2. The Desktop page is disabled by default; enable UniFi in Plugins and enter the API key in its masked secret field. Hermes stores it in the selected profile as `UNIFI_API_KEY`. No endpoint setting exists.

The `/unifi` page, sidebar entry, and “Open UniFi” command provide Overview, Sites, Devices, and ISP Health. Shared SDK React Query polls every 60 seconds. Loading, unconfigured, empty, partial-error, stale refresh failure, and degraded states are explicit. No live API access is needed for tests or previews.

Unofficial integration. UniFi is a trademark of Ubiquiti Inc. This project is not affiliated with or endorsed by Ubiquiti.

## Data contract

Only these fixed upstream GET paths are used at `https://api.ui.com/v1`:

| View | Path | Projection |
| --- | --- | --- |
| Sites | `/sites` | Name, description, timezone, device totals/offline/update counts, WAN uptime |
| Devices | `/devices` | Name, model, product line, status, firmware version/status, available version |
| ISP Health | `/isp-metrics/5m` | Latest timestamped WAN period per site/host pair |
| Overview | The three paths above | Counts and health flags derived from the projections |

The local routes are GET `/health`, `/overview`, `/sites`, `/devices`, `/isp`. View success is `{ok: true, data: ...}`. Failures use `HTTPException.detail = {code, message}`. Health always returns 200, configuration state, `connected: null`, `read_only: true`, and version; it never probes UniFi.

Sites and devices currently show the first upstream page. A returned pagination token sets `partial: true` and a visible notice; counts are explicitly partial. No raw token is returned. Overview retains available summaries if another endpoint fails. ISP rows use temporary numbered site/host labels, never stable IDs; row numbers are not stable across refreshes.

The evidence is the supplied official Site Manager v1 snapshot (`unifi-openapi.json`). Its success envelope contains `data`, `httpStatusCode`, and `traceId`. The documented metric intervals are `5m` and `1h`; this release fixes `5m`. Site metadata and aggregate fields follow the snapshot's `/v1/sites` official example, which warns that fields vary with Network version. Literal Unknown means not reported; null and empty display values use an em dash. No requested display field was omitted for lack of evidence. ISP latency, downtime, uptime, and packet-loss units are not specified in the supplied schema, so unit labels are deliberately omitted instead of guessed. Download/upload use the documented `kbps` field names.

MAC/IP addresses, raw identifiers, connected clients and client counts, trace IDs, historical metric arrays, and arbitrary upstream fields are excluded. Address-like or known identifier values inside names are suppressed too. Hosts are unnecessary for this overview and are not requested.

## Local verification

Use Python 3.11+ and Node 22+:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
node --check desktop/plugin.js
node --check scripts/render_screenshot.cjs
for view in overview sites devices isp; do
  node --experimental-vm-modules scripts/render_screenshot.cjs "$view" "/tmp/$view.html"
  cmp "/tmp/$view.html" "docs/screenshots/$view.html"
done
hermes plugins doctor . --ci
git diff --check
```

Tests block socket connections and DNS and mock every transport. Route tests exercise the registered endpoints and Starlette route/method matching without a threaded HTTP test server. `scripts/render_screenshot.cjs` renders the real Desktop component with synthetic SDK/React stand-ins in a VM without network primitives. Its deterministic artifacts cover [Overview](docs/screenshots/overview.html), [Sites](docs/screenshots/sites.html), [Devices](docs/screenshots/devices.html), and [ISP Health](docs/screenshots/isp.html); these are static screenshot-ready previews, not captured Hermes Desktop screenshots. Pass `sites`, `devices`, or `isp` and optionally an output path to render another view. Preview fixtures are checked against the Python sanitizers.

The reference structure is hermes-unraid commit `48deec3dfd9bbc0b00731412635fa2dc06263d03`. Root registration is intentionally present and registers no agent tools or hooks. This release adds no mutation controls, notifications, telemetry, exports, persistence, MCP, SSH, or LLM features.
