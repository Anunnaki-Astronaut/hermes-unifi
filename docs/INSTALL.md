# Install and set up Hermes UniFi

Hermes for UniFi requires Hermes Agent and Desktop 0.22.2 or newer. Start with the data source you need: Site Manager for site, device, and ISP summaries; your local UniFi console for connected clients and detailed diagnostics. You can use either or both. The Hermes backend, not the Desktop window, must be able to reach each source.

## Desktop installation

1. Open [Install in Hermes](hermes://plugin/install?repo=Anunnaki-Astronaut/hermes-unifi&enable=1), or use **Capabilities → Plugins → Install from Git** with `Anunnaki-Astronaut/hermes-unifi`.
2. Review the source and select both **Desktop** and **Agent/backend**.
3. Confirm installation and enable **UniFi** in **Capabilities → Plugins**.

For a remote backend, the Desktop part belongs on the Desktop computer; the Agent/backend part must be installed and enabled on the connected backend host. Installing only Desktop leaves the backend routes unavailable (`Plugin not found`).

## Command-line installation

On the backend host, for the intended Hermes profile:

```sh
hermes plugins install Anunnaki-Astronaut/hermes-unifi --enable
```

If already installed but disabled:

```sh
hermes plugins enable unifi
```

For a remote backend, also install the local Desktop part through **Capabilities → Plugins → Install from Git**.

## Create and configure the Site Manager API key (cloud views)

1. Sign in to `unifi.ui.com`.
2. Go to **Settings → API Keys** and create a new API key.
3. Copy the key once when shown and store it securely.
4. Select the intended backend/profile in Hermes Desktop.
5. Open **Settings → Plugins → UniFi**, enter the key into the masked **Site Manager API key** field, and save.

Official sources: [UniFi API introduction](https://help.ui.com/hc/en-us/articles/30076656117655-Getting-Started-with-the-Official-UniFi-API) and [Site Manager API setup](https://developer.ui.com/site-manager-api/gettingstarted).

The profile secret is `UNIFI_API_KEY`. Do not paste it into chat, URLs, JavaScript, screenshots, issues, or Git. No key belongs in `plugin.js` or ordinary plugin settings files. The key is not exposed to Desktop JavaScript.

There is no configurable cloud endpoint. The backend makes only fixed read-only GET requests under `https://api.ui.com/v1` for `/sites`, `/devices`, and `/isp-metrics/5m`.

## Configure the local console (Diagnostics and Clients)

1. Open **UniFi Network → Integrations** on your console and create a dedicated Network API key if your version and account allow it. Prefer limited permissions and a finite expiry where offered. Copy the key when it appears and store it securely. This isn't your Site Manager key or your console password.
2. In Hermes Desktop, select the intended backend/profile and open **UniFi → gear → Open Agent settings**. Set **UniFi console host (local)** to the console's private LAN address or local hostname, for example `192.168.1.1` or `unifi.local`. Do not include `https://`, a path, or credentials. Public addresses and non-local hostnames are rejected.
3. Enter the key in the masked **Network API key (console)** field and save. The profile secret is `UNIFI_NETWORK_API_KEY`. Leave **Show IP addresses** off unless you want IPs displayed. MAC addresses are never shown regardless of this setting.
4. Open **Clients**. If it loads, leave the certificate pin blank unless you already use one. If it reports `certificate_untrusted`, follow the Firefox steps below; there's no need to create a new key.

The backend makes only fixed read-only GET requests under `https://<console-host>/proxy/network/integration/v1`: `/info`, `/sites`, and per-site `/devices`, `/devices/{id}`, `/devices/{id}/statistics/latest`, `/clients`, `/wans`, `/networks`, and `/wifi/broadcasts`. See [Ubiquiti's Network API guide](https://help.ui.com/hc/en-us/articles/30076656117655-Getting-Started-with-the-Official-UniFi-API#local-application-apis).

### Copy the local console's SHA-256 fingerprint in Firefox

1. On the private network, open Firefox and enter `https://` followed by the **exact console address** saved in Hermes. Use the local address, **not** `unifi.ui.com`.
2. On the certificate warning, click **Advanced… → View the site’s certificate**. This opens the certificate viewer without accepting the warning. Do not click **Proceed (Risky)**.
3. In the viewer, select the console's own certificate (the first tab if a chain is shown). Scroll to **Fingerprints**, select the entire **SHA-256** value, and copy it (`⌘C` on Mac, `Ctrl+C` on Windows/Linux). Copy the value only, not the label, **SHA-1**, or **Signature Algorithm**. Hermes accepts the full 64 hex digits with or without colons.
4. Once you have confirmed the fingerprint, paste it into **UniFi → gear → Open Agent settings → Console certificate SHA-256 pin** and save. Return to **Clients → Refresh**, then check **Diagnostics**. A **Site Manager + console** badge by itself is not proof the console connection worked; look for actual data in both views.

Firefox shows which certificate the address presented; that alone does not prove the identity of a self-signed console. Verify the initial fingerprint through an already-trusted source when available. If you choose to trust it on first use on your own LAN, do so only for the exact console address you recognize. Hermes then checks that fingerprint before sending the key on each connection. If the pin changes unexpectedly, investigate before replacing it. No SSH, Debug, browser exception, certificate upload, or router restart is needed for the Firefox steps.

## First-run verification

Open **UniFi** from the sidebar or **Open UniFi** from the command palette. Check Overview, Diagnostics, Sites, Devices, ISP Health, and Clients. Configured status alone does not prove connectivity: the local health route never probes UniFi. Opening data views performs the read-only API requests. Views that need a source you have not configured say so instead of failing.

If UniFi does not appear in the sidebar, install and enable the Desktop part on the computer running Desktop, then rescan plugins or restart Desktop. If UniFi opens but its health check fails, install and enable the Agent/backend part on the connected backend.

`Not configured` means the selected profile lacks a usable key for the view's source. `Plugin not found` means the connected backend lacks the enabled plugin. Authentication failures require checking the relevant key and account access; rate limits require waiting for the cooldown. `certificate_untrusted` and `certificate_mismatch` mean the console certificate pin needs confirming; `console_unreachable` means the backend cannot reach the host on the private network. Missing values and Unknown are allowed, and partial notices mean a bounded read stopped before completion. No live request is needed for development tests or synthetic previews.

To confirm the agent tools, ask Hermes "how is my network doing?"; it should call `unifi_status` and answer in one paragraph without any MAC address or key.

Site / host numbers and device/client handles are temporary and may change after refresh. They are presentation-only row numbers, not identities, and must not be used to correlate data across refreshes.

## Update or remove

To update the backend:

```sh
hermes plugins update unifi
```

Then use **Capabilities → Plugins → Rescan** or restart Desktop to refresh its local copy. Check both parts when using a remote backend.

To remove the backend:

```sh
hermes plugins remove unifi
```

Disable or remove the Desktop part through **Capabilities → Plugins**. Manage any retained profile secrets in Hermes, and revoke unused API keys through Site Manager and the console's Integrations page.

See [README](../README.md) for troubleshooting, [SECURITY](../SECURITY.md) for security controls, and [PRIVACY](../PRIVACY.md) for data handling. This version diagnoses and recommends but cannot change the network; its agent tools are read-only.
