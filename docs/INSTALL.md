# Install and set up Hermes UniFi

Version 0.1.0 requires Hermes Agent and Desktop >=0.22.2, UniFi Site Manager access, a Site Manager API key, and backend internet access to `https://api.ui.com`. Repository installation requires the public repository to be available.

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

## Create and configure the API key

1. Sign in to `unifi.ui.com`.
2. Go to **Settings → API Keys** and create a new API key.
3. Copy the key once when shown and store it securely.
4. Select the intended backend/profile in Hermes Desktop.
5. Open **Settings → Plugins → UniFi**, enter the key into the masked API-key field, and save.

Official sources: [UniFi API introduction](https://help.ui.com/hc/en-us/articles/30076656117655-Getting-Started-with-the-Official-UniFi-API) and [Site Manager API setup](https://developer.ui.com/site-manager-api/gettingstarted).

The profile secret is `UNIFI_API_KEY`. Do not paste it into chat, URLs, JavaScript, screenshots, issues, or Git. No key belongs in `plugin.js` or ordinary plugin settings files. The key is not exposed to Desktop JavaScript.

There is no configurable endpoint. The backend makes only fixed read-only GET requests under `https://api.ui.com/v1` for `/sites`, `/devices`, and `/isp-metrics/5m`.

## First-run verification

Open **UniFi** from the sidebar or **Open UniFi** from the command palette. Check Overview, Sites, Devices, and ISP Health. Configured status alone does not prove connectivity: the local health route never probes UniFi. Opening data views performs the read-only API requests.

`Not configured` means the selected profile lacks a usable key. `Plugin not found` means the connected backend lacks the enabled plugin. Authentication failures require checking the Site Manager key and account access; rate limits require waiting for the cooldown. Missing values and Unknown are allowed, and partial notices mean incomplete first-page results. No live request is needed for development tests or synthetic previews.

Site / host numbers are temporary and may change after refresh. They are presentation-only row numbers, not identities, and must not be used to correlate data across refreshes.

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

Disable or remove the Desktop part through **Capabilities → Plugins**. Manage any retained profile secret in Hermes, and revoke an unused API key through Site Manager.

See [README](../README.md) for troubleshooting, [SECURITY](../SECURITY.md) for security controls, and [PRIVACY](../PRIVACY.md) for data handling. This monitor cannot diagnose, repair, or change the network and exposes no agent tool.
