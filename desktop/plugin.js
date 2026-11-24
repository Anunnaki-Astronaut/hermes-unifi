import React, { useState, useSyncExternalStore } from 'react';
import { jsx, jsxs } from 'react/jsx-runtime';
import { Button, ErrorState, GlyphSpinner, StatusDot, useQuery, host, ROUTES_AREA, SIDEBAR_NAV_AREA, PALETTE_AREA } from '@hermes/plugin-sdk';
import * as sdk from '@hermes/plugin-sdk';

const ROUTE = '/unifi';
const PRODUCT_ICON = 'target';
const PLUGIN_VERSION = '0.4.0';
let ctx;
let preferences;
const activeProfile = () => host.state?.profile?.get?.() || 'default';
// An empty connection segment keeps older or unscoped hosts profile-only.
const activeScope = () => `${encodeURIComponent(host.state?.connectionId?.get?.() ?? '')}:${encodeURIComponent(activeProfile())}`;
function subscribeScope(listener) {
  const unsubscribeConnection = host.state?.connectionId?.subscribe?.(listener);
  const unsubscribeProfile = host.state?.profile?.subscribe?.(listener);
  return () => { unsubscribeConnection?.(); unsubscribeProfile?.(); };
}
const openAgentSettings = () => host.navigate(`/settings?${new URLSearchParams({
  tab: 'plugins', agent: 'unifi', profile: activeProfile(),
})}`);
const openSettings = () => host.navigate(sdk.pluginSettingsHref?.('unifi') ?? '/settings?tab=plugins&plugin=unifi');
const icon = (name, size) => sdk.Codicon ? jsx(sdk.Codicon, { name, size }) : jsx('span', { className: `codicon codicon-${name}`, style: { fontSize: size }, 'aria-hidden': true });
const APPEARANCE = {
  match: ['Match Desktop', 'device-desktop'],
  system: ['System', 'color-mode'],
  light: ['Light', 'sun'],
  dark: ['Dark', 'moon'],
};
const validAppearance = value => typeof value === 'string' && Object.hasOwn(APPEARANCE, value) ? value : 'match';
const MODES = ['light', 'dark'];
const FIELDS = { background: 'Background', panel: 'Panels', text: 'Text', accent: 'Accent', selected: 'Selected row' };
const PRESETS = {
  Daybook: {
    light: { background: '#F8FAF7', panel: '#EEF4EF', text: '#17302A', accent: '#27674E', selected: '#D5EBDD' },
    dark: { background: '#111A19', panel: '#1A2725', text: '#F3F8F5', accent: '#A8EBC9', selected: '#304D3D' },
  },
  Dusk: {
    light: { background: '#FCF6FA', panel: '#FFFFFF', text: '#37253F', accent: '#794526', selected: '#EEDDEC' },
    dark: { background: '#1B1725', panel: '#2A2337', text: '#F5EAF7', accent: '#FFBC91', selected: '#483753' },
  },
  Coast: {
    light: { background: '#F2FAFB', panel: '#FFFFFF', text: '#163B42', accent: '#166373', selected: '#D2EAF0' },
    dark: { background: '#10252C', panel: '#193640', text: '#E5F7FA', accent: '#8AD9E6', selected: '#2C4D58' },
  },
  Marigold: {
    light: { background: '#FFF9E4', panel: '#F6E7AE', text: '#352600', accent: '#725000', selected: '#F9DF82' },
    dark: { background: '#211900', panel: '#342800', text: '#FFF0BE', accent: '#FFCD4E', selected: '#523D00' },
  },
  Cobalt: {
    light: { background: '#F1F5FF', panel: '#E1E9FF', text: '#12234D', accent: '#234AC5', selected: '#CFDDFF' },
    dark: { background: '#10182F', panel: '#1B2850', text: '#E8F0FF', accent: '#9FB4FF', selected: '#304787' },
  },
  Anunnaki: {
    light: { background: '#FAF8F3', panel: '#EAE2D3', text: '#1C1B1A', accent: '#704718', selected: '#E5D3B7' },
    dark: { background: '#0C1420', panel: '#64442D', text: '#E9EFF6', accent: '#F1BE77', selected: '#533829' },
  },
};
const hexColor = value => typeof value === 'string' && value.length === 7 && /^#[\da-f]{6}$/i.test(value) ? value.toUpperCase() : null;

function contrast(a, b) {
  const luminance = hex => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map(n => n <= .04045 ? n / 12.92 : ((n + .055) / 1.055) ** 2.4)
    .reduce((total, n, i) => total + n * [.2126, .7152, .0722][i], 0);
  const x = luminance(a), y = luminance(b);
  return (Math.max(x, y) + .05) / (Math.min(x, y) + .05);
}

function inspectPalette(value) {
  const palette = {}, errors = [];
  for (const [field, label] of Object.entries(FIELDS)) {
    palette[field] = hexColor(value?.[field]);
    if (!palette[field]) errors.push(`${label}: enter #RRGGBB.`);
  }
  if (!errors.length) {
    for (const ink of ['text', 'accent']) {
      for (const surface of ['background', 'panel', 'selected']) {
        // Accent on selected surfaces is decorative; all row lettering uses Text.
        const minimum = ink === 'accent' && surface === 'selected' ? 3 : 4.5;
        if (contrast(palette[ink], palette[surface]) < minimum) {
          errors.push(`${FIELDS[ink]} needs ${minimum}:1 against ${FIELDS[surface]}.`);
        }
      }
    }
  }
  return { palette, errors };
}

function validPalette(value) {
  const { palette, errors } = inspectPalette(value);
  return errors.length ? null : palette;
}

function paletteStyle(palette) {
  if (!palette) return undefined;
  const { background, panel, text, accent, selected } = palette;
  return {
    '--unifi-canvas': background, '--ui-bg-card': panel,
    '--ui-text-primary': text, '--ui-text-secondary': text,
    '--unifi-accent': accent, '--unifi-selected': selected,
    '--ui-stroke-secondary': `color-mix(in srgb, ${text} 30%, ${background})`,
  };
}

function createPreferences(storage) {
  const snapshots = new Map(), listeners = new Set();
  const keyFor = (scope, field) => `unifi.${field}.v1.${scope}`;
  const read = (key, validate) => validate(storage?.get?.(key));
  return {
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    get(scope, field, validate) {
      const key = keyFor(scope, field);
      if (!snapshots.has(key)) {
        try { snapshots.set(key, read(key, validate)); }
        catch { snapshots.set(key, validate(undefined)); }
      }
      return snapshots.get(key);
    },
    save(scope, field, value, validate) {
      if (scope !== activeScope() || typeof storage?.set !== 'function') return false;
      const key = keyFor(scope, field);
      try {
        storage.set(key, value);
        const persisted = read(key, validate);
        if (JSON.stringify(persisted) !== JSON.stringify(value)) return false;
        snapshots.set(key, persisted);
        listeners.forEach(fn => fn());
        return true;
      } catch { return false; }
    },
  };
}

let systemMedia;
function darkMedia() {
  try { return systemMedia ??= globalThis.window?.matchMedia?.('(prefers-color-scheme: dark)'); }
  catch { return undefined; }
}
const systemDark = () => darkMedia()?.matches === true;
const noSubscription = () => () => {};
function subscribeSystem(listener) {
  const media = darkMedia();
  if (media?.addEventListener) {
    media.addEventListener('change', listener);
    return () => media.removeEventListener('change', listener);
  }
  if (media?.addListener) {
    media.addListener(listener);
    return () => media.removeListener(listener);
  }
  return () => {};
}

function useAppearance() {
  const scope = useSyncExternalStore(subscribeScope, activeScope);
  const store = preferences;
  const choice = useSyncExternalStore(store.subscribe, () => store.get(scope, 'appearance', validAppearance));
  const prefersDark = useSyncExternalStore(choice === 'system' ? subscribeSystem : noSubscription, systemDark);
  const resolved = choice === 'system' ? (prefersDark ? 'dark' : 'light') : choice;
  return { scope, choice, resolved, choose(next) {
    if (store === preferences && validAppearance(next) === next) store.save(scope, 'appearance', next, validAppearance);
  } };
}

function useSavedPalette(scope, mode) {
  const store = preferences;
  return useSyncExternalStore(store.subscribe, () => MODES.includes(mode) ? store.get(scope, `palette.${mode}`, validPalette) : null);
}
const loaders = {
  health: () => ctx.rest('/health'),
  overview: () => ctx.rest('/overview'),
  diagnostics: () => ctx.rest('/diagnostics'),
  sites: () => ctx.rest('/sites'),
  devices: () => ctx.rest('/devices'),
  isp: () => ctx.rest('/isp'),
  clients: () => ctx.rest('/console/clients'),
};
const labels = { overview: 'Overview', diagnostics: 'Diagnostics', sites: 'Sites', devices: 'Devices', isp: 'ISP Health', clients: 'Clients' };
// Which configured source each view needs: 'cloud' (Site Manager key), 'console' (local Network API), or 'any'.
const sources = { overview: 'cloud', diagnostics: 'any', sites: 'cloud', devices: 'cloud', isp: 'cloud', clients: 'console' };
const columns = {
  sites: { name: 'Name', description: 'Description', timezone: 'Timezone', totalDevices: 'Devices', offlineDevices: 'Offline', pendingUpdates: 'Updates', wanUptime: 'WAN uptime' },
  devices: { name: 'Name', model: 'Model', productLine: 'Product line', status: 'Status', version: 'Version', firmwareStatus: 'Firmware', updateAvailable: 'Available version' },
  isp: { label: 'Site / host', metricTime: 'Latest period (UTC)', ispName: 'ISP', avgLatency: 'Average latency', maxLatency: 'Maximum latency', download_kbps: 'Download (kbps)', upload_kbps: 'Upload (kbps)', downtime: 'Downtime', packetLoss: 'Packet loss', uptime: 'Uptime' },
  clients: { name: 'Name', type: 'Connection', uplinkName: 'Connected via', accessType: 'Access', authorized: 'Authorized', connectedAt: 'Connected since (UTC)', ipAddress: 'IP address' },
};
const descriptions = {
  overview: 'Reported counts and health across sites, devices, and ISP records.',
  diagnostics: 'Plain-English findings and recommendations from the local console and Site Manager. Nothing here changes the network.',
  sites: 'Device counts, pending updates, and WAN uptime by site.',
  devices: 'Reported device status, installed versions, and firmware availability.',
  isp: 'ISP metrics for the latest reported period at each site / host.',
  clients: 'Clients currently connected through the local console. MAC addresses are never shown; IP addresses only when enabled in settings.',
};
const numericColumns = new Set(['totalDevices', 'offlineDevices', 'pendingUpdates', 'wanUptime', 'avgLatency', 'maxLatency', 'download_kbps', 'upload_kbps', 'downtime', 'packetLoss', 'uptime']);
const enumLabels = { upToDate: 'Up to date', updateAvailable: 'Update available', online: 'Online', offline: 'Offline', connected: 'Connected', disconnected: 'Disconnected', pending: 'Pending', updating: 'Updating', unknown: 'Unknown', WIRED: 'Wired', WIRELESS: 'Wireless', VPN: 'VPN', TELEPORT: 'Teleport', DEFAULT: 'Default', GUEST: 'Guest' };
const enumColumns = new Set(['status', 'firmwareStatus', 'type', 'accessType']);
const severityLabels = { critical: 'Critical', warning: 'Warning', info: 'Note', ok: 'OK' };
const fixLabels = { RESTART_DEVICE: 'restart the device', POWER_CYCLE_PORT: 'power-cycle the port' };
function displayValue(key, value) {
  if (value == null || (typeof value === 'string' && value.trim() === '')) return '—';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (!enumColumns.has(key)) return value;
  if (Object.hasOwn(enumLabels, value)) return enumLabels[value];
  return typeof value === 'string' && /^[a-z]+$/.test(value) ? value[0].toUpperCase() + value.slice(1) : value;
}
function semanticTone(value) {
  if (['healthy', 'online', 'connected', 'upToDate'].includes(value)) return 'good';
  if (['warning', 'updateAvailable', 'degraded', 'partial', 'updating', 'pending'].includes(value)) return 'warn';
  if (['offline', 'disconnected', 'error', 'errors'].includes(value)) return 'bad';
  return 'muted';
}
function severityTone(severity) {
  return severity === 'critical' ? 'bad' : severity === 'warning' ? 'warn' : severity === 'ok' ? 'good' : 'muted';
}
function rowTone(row) {
  const status = semanticTone(row.status);
  if (status === 'bad' || row.offlineDevices > 0) return 'bad';
  if (status === 'warn' || row.pendingUpdates > 0 || (typeof row.wanUptime === 'number' && row.wanUptime < 100)
    || row.packetLoss > 0 || row.downtime > 0 || row.authorized === false) return 'warn';
  return 'muted';
}
function summaryTone(summary) {
  if (semanticTone(summary.status) === 'bad') return 'bad';
  if (summary.degraded || summary.partial) return 'warn';
  return semanticTone(summary.status ?? 'healthy');
}
function cell(key, value, rowAttention = false) {
  const label = displayValue(key, value);
  const tone = semanticTone(value);
  const muted = label === '—' || label === 'Unknown' || ((key === 'status' || key === 'firmwareStatus') && tone === 'muted');
  const pill = !muted && (key === 'status' || key === 'firmwareStatus');
  return jsxs('td', { className: numericColumns.has(key) ? 'numeric' : undefined, children: [jsx('span', {
    className: muted ? 'muted' : pill ? `pill ${tone}` : undefined, children: label,
  }), rowAttention ? jsx('span', { className: 'row-note', children: 'Needs attention' }) : null] }, key);
}
const CSS = `
.unifi{--unifi-good:var(--ui-success);--unifi-warn:var(--ui-yellow);--unifi-bad:var(--ui-red);--unifi-muted:var(--ui-text-secondary);padding:24px;color:var(--ui-text-primary);max-width:1400px;min-width:0;box-sizing:border-box;margin:auto}
.unifi *{box-sizing:border-box}.unifi h1,.unifi h2,.unifi h3,.unifi p{margin:0}
.unifi .topbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:20px}
.unifi .brand{display:flex;align-items:center;gap:10px}.unifi h1{font-size:24px;font-weight:700;line-height:1.3}
.unifi .connection{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--ui-text-secondary)}
.unifi .readonly,.unifi .pill{display:inline-block;border:1px solid var(--ui-stroke-secondary);border-radius:5px;padding:3px 7px;font-size:12px;line-height:1.4;white-space:nowrap}
.unifi .refresh{margin-left:auto}
.unifi button{font:inherit;cursor:pointer;min-height:36px}.unifi button:disabled{cursor:default;opacity:.5}
.unifi .refresh button{background:transparent;border:1px solid var(--ui-stroke-secondary);color:var(--ui-text-primary);border-radius:6px;padding:6px 12px;font-size:13px}
.unifi nav{display:flex;gap:4px;padding:4px;width:fit-content;max-width:100%;flex-wrap:wrap;border:1px solid var(--ui-stroke-secondary);border-radius:8px;background:var(--ui-bg-card)}
.unifi nav button{background:transparent;border:1px solid transparent;border-radius:5px;color:var(--ui-text-secondary);padding:7px 14px;font-size:13px}
.unifi nav button[aria-pressed="true"]{color:var(--ui-yellow);border-color:var(--ui-yellow);font-weight:600}
.unifi nav button:hover{color:var(--ui-text-primary)}.unifi button:focus-visible,.unifi .table:focus-visible{outline:2px solid var(--ui-yellow);outline-offset:3px}
.unifi .view-heading{margin:24px 0 18px}.unifi .view-heading h2{font-size:18px;margin-bottom:6px}
.unifi .view-heading p{font-size:13px;line-height:1.6;color:var(--ui-text-secondary)}
.unifi .cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.unifi article{padding:16px;border:1px solid var(--ui-stroke-secondary);border-radius:8px;background:var(--ui-bg-card)}
.unifi article h2{font-size:13px;font-weight:500;color:var(--ui-text-secondary)}.unifi .count{display:block;font-size:28px;line-height:1.3;font-variant-numeric:tabular-nums;margin:10px 0}
.unifi .state{display:flex;align-items:center;gap:8px;font-size:12px;line-height:1.5}
.unifi .state:before{content:'';width:8px;height:8px;flex-shrink:0;border:1px solid currentColor;border-radius:50%}
.unifi .good{--unifi-tone:var(--unifi-good);color:var(--unifi-good)}.unifi .warn{--unifi-tone:var(--unifi-warn);color:var(--unifi-warn)}.unifi .bad{--unifi-tone:var(--unifi-bad);color:var(--unifi-bad)}.unifi .muted{--unifi-tone:var(--unifi-muted);color:var(--unifi-muted)}
.unifi .good .state:before{background:currentColor}.unifi .partial .state:before{border-radius:0}.unifi .attention .state:before{border-radius:0;transform:rotate(45deg)}
.unifi article.good,.unifi article.warn,.unifi article.bad,.unifi article.muted{color:var(--ui-text-primary);border-top-color:var(--unifi-tone)}.unifi article .state{color:var(--unifi-tone)}
.unifi .table-shell{min-width:0;border:1px solid var(--ui-stroke-secondary);border-radius:8px;background:var(--ui-bg-card);overflow:hidden}
.unifi .table-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 16px;border-bottom:1px solid var(--ui-stroke-secondary)}.unifi .table-heading span{font-size:12px;color:var(--ui-text-secondary);font-variant-numeric:tabular-nums}
.unifi .table{overflow:auto;max-height:60vh;isolation:isolate}.unifi .table:focus-visible{outline-offset:-3px}
.unifi table{width:100%;border-collapse:separate;border-spacing:0;font-size:13px}
.unifi th,.unifi td{text-align:left;padding:12px 16px;border-bottom:1px solid var(--ui-stroke-secondary);white-space:nowrap}
.unifi th{position:sticky;top:0;z-index:1;background:var(--ui-bg-card);font-size:12px;font-weight:600;color:var(--ui-text-secondary)}
.unifi .numeric{text-align:right;font-variant-numeric:tabular-nums}.unifi tbody tr:last-child td{border-bottom:0}
.unifi tbody tr:hover{background:var(--ui-stroke-secondary)}.unifi tr.row-attention{color:var(--ui-text-primary)}.unifi tr.row-attention td:first-child{border-left:3px solid var(--unifi-tone);padding-left:13px}
.unifi .row-note{display:block;margin-top:4px;font-size:11px;color:var(--unifi-tone)}
.unifi .notice{padding:12px 14px;border:1px solid var(--ui-stroke-secondary);border-left:3px solid var(--unifi-tone);border-radius:5px;margin:0 0 16px;font-size:13px;line-height:1.6}
.unifi .notice.good,.unifi .notice.warn,.unifi .notice.bad,.unifi .notice.muted{color:var(--ui-text-primary)}
.unifi .empty{padding:16px;color:var(--ui-text-secondary)}
.unifi .findings{display:grid;gap:12px;margin-top:16px;padding:0;list-style:none}
.unifi .finding{padding:14px 16px;border:1px solid var(--ui-stroke-secondary);border-left:3px solid var(--unifi-tone);border-radius:8px;background:var(--ui-bg-card);color:var(--ui-text-primary)}
.unifi .finding-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px}.unifi .finding h3{font-size:14px;font-weight:600;line-height:1.4}
.unifi .finding p{font-size:13px;line-height:1.6}.unifi .finding .action{margin-top:6px}.unifi .finding .fix{margin-top:6px;font-size:12px;color:var(--ui-text-secondary)}
.unifi footer{margin-top:24px;padding-top:16px;border-top:1px solid var(--ui-stroke-secondary);font-size:12px;color:var(--ui-text-secondary)}
.unifi footer .disclaimer{margin-bottom:12px;line-height:1.6}
.unifi footer h2{font-size:12px;color:var(--ui-text-primary);font-weight:600}.unifi footer ul{display:flex;flex-wrap:wrap;gap:8px 28px;padding-left:16px;margin:10px 0 0;line-height:1.5}
@media(max-width:800px){.unifi{padding:16px}.unifi .connection{order:3;flex-basis:100%}.unifi .cards{gap:8px}.unifi article{padding:12px}.unifi nav{width:100%}.unifi nav button{flex:1;padding:7px 10px}}
@media(max-width:520px){.unifi .cards{grid-template-columns:1fr}.unifi footer ul{display:grid;gap:6px}.unifi .readonly{font-size:11px}}
`;

const CHROME_CSS = `
.unifi-shell{container:unifi-pane / inline-size;color:var(--ui-text-primary);background:var(--unifi-canvas,var(--ui-bg-editor));min-width:0;min-height:100%;font-size:13px}
.unifi-shell *{box-sizing:border-box}
.unifi-shell .topbar{display:flex;align-items:center;justify-content:space-between;gap:8px 16px;flex-wrap:wrap;margin:0;padding:12px 18px;border-bottom:1px solid var(--ui-stroke-secondary);background:var(--ui-bg-card)}
.unifi-shell .brand,.unifi-shell .brand-title,.unifi-shell .top-actions{display:flex;align-items:center;gap:10px;min-width:0}
.unifi-shell .brand-title{align-items:baseline;flex-wrap:wrap;gap:0 8px}
.unifi-shell .brand-title h1{font-size:20px;font-weight:750;letter-spacing:-.025em;line-height:1.2}
.unifi-shell .app-version{font-size:11px;color:var(--ui-text-secondary)}
.unifi-shell .brand-icon{display:grid;place-items:center;width:36px;height:36px;flex:none;border-radius:10px;background:var(--unifi-selected,var(--ui-bg-tertiary));color:var(--ui-text-primary)}
.unifi-shell .top-actions{flex-wrap:wrap;gap:8px}
.unifi-shell .top-actions .connection{order:initial;flex-basis:auto}
.unifi-shell .top-actions .refresh{margin-left:0}
.unifi-shell .unifi-body{padding:0 18px 20px;min-width:0}
.unifi-shell.unifi{padding:0}
.unifi-shell .unifi-body nav{background:transparent;border:0;border-bottom:1px solid var(--ui-stroke-secondary);border-radius:0;padding:0;width:100%;gap:3px}
.unifi-shell .unifi-body nav button{border:0;border-bottom:3px solid transparent;border-radius:0;margin-bottom:-1px;padding:8px;min-height:44px}
.unifi-shell .unifi-body nav button[aria-pressed=true]{color:var(--ui-text-primary);background:var(--unifi-selected,transparent);border-bottom-color:var(--unifi-accent,var(--ui-accent))}
.unifi-shell .ui-control{display:inline-flex;align-items:center;justify-content:center;gap:.45rem;min-height:34px;padding:5px 10px;border:1px solid var(--ui-stroke-secondary);border-radius:6px;background:var(--ui-bg-card);color:var(--ui-text-primary);font:inherit;font-weight:650;cursor:pointer}
.unifi-shell .ui-control:hover{background:var(--unifi-selected,var(--ui-bg-tertiary))}
.unifi-shell .ui-control:focus-visible{outline:2px solid var(--unifi-accent,var(--ui-accent));outline-offset:2px}
.unifi-shell .settings-gear{width:36px;height:36px;padding:0}
.unifi-shell .appearance-control{display:inline-flex;gap:5px}
.unifi-shell .appearance-option{width:28px;height:28px;min-height:28px;padding:0;color:var(--ui-text-secondary)}
.unifi-shell .appearance-option[aria-pressed=true]{color:var(--ui-text-primary);background:var(--unifi-selected,var(--ui-bg-tertiary));border-color:var(--unifi-accent,var(--ui-accent))}
.unifi-shell .appearance-option:focus-visible{outline:2px solid var(--unifi-accent,var(--ui-accent));outline-offset:2px}
.unifi-shell .mode-sun{display:block;width:7px;height:7px;border:1px solid currentColor;border-radius:50%;box-shadow:0 -6px 0 -2px currentColor,0 6px 0 -2px currentColor,-6px 0 0 -2px currentColor,6px 0 0 -2px currentColor,-4px -4px 0 -2px currentColor,4px 4px 0 -2px currentColor,4px -4px 0 -2px currentColor,-4px 4px 0 -2px currentColor}
.unifi-shell .mode-moon{display:block;width:12px;height:12px;border-radius:50%;box-shadow:-2px 2px 0 0 currentColor;transform:translate(1px,-1px)}
.unifi-shell[data-appearance=light]{color-scheme:light;--unifi-canvas:#F8FAF7;--ui-bg-card:#EEF4EF;--ui-text-primary:#17302A;--ui-text-secondary:#17302A;--unifi-accent:#27674E;--unifi-selected:#D5EBDD;--ui-stroke-secondary:#A8BAB2}
.unifi-shell[data-appearance=dark]{color-scheme:dark;--unifi-canvas:#111A19;--ui-bg-card:#1A2725;--ui-text-primary:#F3F8F5;--ui-text-secondary:#F3F8F5;--unifi-accent:#A8EBC9;--unifi-selected:#304D3D;--ui-stroke-secondary:#445953}
.unifi-shell[data-appearance]:not([data-appearance=match]) :is(button,.table):focus-visible{outline-color:var(--unifi-accent)}
.unifi-shell[data-appearance]:not([data-appearance=match]) tbody tr:hover{background:var(--unifi-selected)}
.unifi-shell[data-appearance]:not([data-appearance=match]) :is(.pill.good,.pill.warn,.pill.bad,.row-note,article .state){color:var(--ui-text-primary)}
.unifi-shell[data-appearance]:not([data-appearance=match]) .pill:is(.good,.warn,.bad){border-inline-start:3px solid var(--unifi-tone)}
.unifi-shell[data-appearance]:not([data-appearance=match]) article .state::before{color:var(--unifi-tone)}
.unifi-settings .settings-content{max-width:1100px;margin-inline:auto;padding:24px clamp(16px,5cqi,56px) 40px}
.unifi-settings :is(h1,h2,h3,p){margin:0}
.unifi-settings .settings-brand{display:flex;align-items:baseline;gap:24px;padding-bottom:18px}
.unifi-settings .settings-brand strong{text-transform:uppercase;color:var(--ui-text-primary)}
.unifi-settings p,.unifi-settings .settings-brand span{color:var(--ui-text-secondary);line-height:1.5}
.unifi-settings .settings-section{border-top:1px solid var(--ui-stroke-secondary);padding-block:16px 20px}
.unifi-settings .settings-heading{display:flex;flex-wrap:wrap;align-items:flex-start;justify-content:space-between;gap:12px 20px}
.unifi-settings h1{font-size:34px;line-height:1.16;letter-spacing:-.025em}
.unifi-settings h2{font-size:21px;line-height:1.25;letter-spacing:-.015em}
.unifi-settings h3{font-size:14px}
.unifi-settings :is(h1,h2,h3)+p{margin-top:4px}
.unifi-settings .settings-intro p{font-size:15px}
.unifi-settings .connections-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px clamp(16px,3.4cqi,36px);margin-top:14px}
.unifi-settings .connection-note{border-top:1px solid var(--ui-stroke-secondary);padding-top:10px}
@container unifi-pane (max-width:35rem){
  .unifi-settings .connections-grid{grid-template-columns:minmax(0,1fr)}
  .unifi-shell .unifi-body{padding-inline:12px}
  .unifi-shell .cards{grid-template-columns:1fr}
}
`;

const MAKER_CSS = `
.unifi-settings .palette-section{position:relative}
.unifi-settings .maker{margin-top:12px}
.unifi-settings .maker summary{list-style:none;width:max-content}
.unifi-settings .maker summary::-webkit-details-marker{display:none}
.unifi-settings .maker summary::after{content:'';width:7px;height:7px;margin:0 3px 3px 8px;border:solid currentColor;border-width:0 1.5px 1.5px 0;transform:rotate(45deg)}
.unifi-settings .maker[open] summary::after{transform:translateY(4px) rotate(225deg)}
.unifi-settings .palette-editor{margin-top:10px;padding:clamp(12px,2cqi,22px);border:1px solid var(--ui-stroke-secondary);border-radius:8px;background:var(--ui-bg-card)}
.unifi-settings .editor-head,.unifi-settings .editor-actions,.unifi-settings .editor-mode{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px 14px}
.unifi-settings .editor-head h3{font-size:20px}
.unifi-settings .editor-grid{display:grid;grid-template-columns:minmax(0,4fr) minmax(0,5fr);gap:16px clamp(16px,4cqi,48px);margin-top:12px}
.unifi-settings .editor-grid>*{min-width:0}
.unifi-settings .presets{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 12px}
.unifi-settings .presets button{flex:1 1 auto;justify-content:flex-start}
.unifi-settings .presets button[aria-pressed=true]{border-color:var(--unifi-accent,var(--ui-accent));background:var(--unifi-selected,var(--ui-bg-tertiary))}
.unifi-settings .preset-dots{display:inline-flex}
.unifi-settings .preset-dots span{width:12px;height:12px;border-radius:50%;border:1px solid var(--ui-stroke-secondary)}
.unifi-settings .palette-field{display:grid;grid-template-columns:minmax(0,1fr) 34px minmax(4.5rem,1fr);align-items:center;gap:8px;margin-top:8px}
.unifi-settings .palette-editor :is(input,select){min-width:0;min-height:32px;max-width:100%;border:1px solid var(--ui-stroke-secondary);border-radius:5px;background:var(--unifi-canvas,var(--ui-bg-editor));color:var(--ui-text-primary);font:inherit}
.unifi-settings .palette-editor :is(input,select):focus-visible{outline:2px solid var(--unifi-accent,var(--ui-accent));outline-offset:2px}
.unifi-settings .palette-editor input[aria-invalid=true]{border-color:var(--ui-red)}
.unifi-settings .palette-field input{width:100%;padding:4px}
.unifi-settings .palette-field input[type=text],.unifi-settings .editor-mode select{padding-inline:9px}
.unifi-settings .network-sample{background:var(--unifi-canvas);color:var(--ui-text-primary);border:1px solid var(--ui-stroke-secondary);border-radius:7px;padding:14px;margin:5px 0 10px}
.unifi-settings .sample-line{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:4px 10px}
.unifi-settings .sample-meta{font-size:11px;margin-bottom:6px}
.unifi-settings .sample-panel{background:var(--ui-bg-card);border-radius:4px;padding:10px 12px;margin-bottom:8px}
.unifi-settings .sample-panel strong{display:block;font-size:24px;letter-spacing:-.02em}
.unifi-settings .sample-track{height:5px;border-radius:9px;background:var(--unifi-selected);margin-top:6px;overflow:hidden}
.unifi-settings .sample-track span{display:block;width:87.5%;height:100%;background:var(--unifi-accent)}
.unifi-settings .sample-row{padding:4px 10px}
.unifi-settings .sample-selected{background:var(--unifi-selected);border-inline-start:2px solid var(--unifi-accent);border-radius:0 4px 4px 0;font-weight:650}
.unifi-settings .sample-status{display:inline-flex;gap:5px;align-items:center}
.unifi-settings .sample-footer{font-size:11px;margin:8px 10px 0}
.unifi-settings .palette-check p{margin-top:4px}
.unifi-settings .palette-check ul{margin:6px 0;padding-inline-start:20px}
.unifi-settings .editor-actions{margin-top:14px;padding-top:12px;border-top:1px solid var(--ui-stroke-secondary)}
.unifi-settings .editor-actions div{display:flex;flex-wrap:wrap;gap:8px}
.unifi-settings .palette-editor .apply{background:var(--unifi-accent,var(--ui-accent));color:var(--unifi-canvas,var(--ui-bg-editor));border-color:transparent}
.unifi-settings .palette-editor .apply:focus-visible{outline-color:var(--unifi-accent,var(--ui-accent))}
.unifi-settings .palette-editor button:disabled{opacity:.55;cursor:not-allowed}
.unifi-settings .palette-result:not(:empty){margin-top:8px}
@container unifi-pane (min-width:41rem){
  .unifi-settings .palette-heading{padding-inline-end:10rem}
  .unifi-settings .maker summary{position:absolute;inset-block-start:14px;inset-inline-end:0}
}
@container unifi-pane (width < 41rem){
  .unifi-settings .editor-grid{grid-template-columns:minmax(0,1fr)}
}
`;

function NetworkSample({ palette }) {
  return jsxs('div', { className: 'network-sample', style: paletteStyle(palette), children: [
    jsxs('div', { className: 'sample-line sample-meta', children: [jsx('strong', { children: 'OVERVIEW' }), 'Sample data'] }),
    jsxs('div', { className: 'sample-panel', children: [
      'Network devices', jsx('strong', { children: '7 of 8 online' }),
      jsx('div', { className: 'sample-track', 'aria-hidden': true, children: jsx('span', {}) }),
    ] }),
    jsxs('div', { className: 'sample-line sample-row sample-selected', children: [
      'Studio access point',
      jsxs('span', { className: 'sample-status', children: [jsx(StatusDot, { tone: 'good' }), 'Online'] }),
    ] }),
    jsxs('div', { className: 'sample-line sample-row', children: ['Active clients', jsx('span', { children: '24 connected' })] }),
    jsxs('div', { className: 'sample-footer', children: [icon('eye', '12px'), ' Read-only'] }),
  ] });
}

function ThemeMaker({ scope, palettes, resolved }) {
  const store = preferences;
  const [editMode, setMode] = useState(null);
  const mode = editMode ?? (resolved === 'dark' ? 'dark' : 'light');
  const label = APPEARANCE[mode][0];
  const [drafts, setDrafts] = useState(() => Object.fromEntries(MODES.map(name => [name, palettes[name] ?? PRESETS.Daybook[name]])));
  const [bases, setBases] = useState(() => Object.fromEntries(MODES.map(name => [name,
    Object.keys(PRESETS).find(preset => JSON.stringify(PRESETS[preset][name]) === JSON.stringify(palettes[name])) ?? 'Daybook',
  ])));
  const [messages, setMessages] = useState({});
  const draft = drafts[mode];
  const { palette, errors } = inspectPalette(draft);
  const preview = errors.length ? palettes[mode] ?? PRESETS.Daybook[mode] : palette;
  const message = text => setMessages(current => ({ ...current, [mode]: text }));
  const replace = value => { setDrafts(current => ({ ...current, [mode]: value })); message(''); };
  const change = (field, value) => {
    setDrafts(current => ({ ...current, [mode]: { ...current[mode], [field]: value } }));
    message('');
  };
  const apply = () => {
    if (errors.length || store !== preferences || scope !== activeScope()) return;
    const saved = store.save(scope, `palette.${mode}`, palette, validPalette);
    message(saved ? `${label} palette saved.${resolved === mode ? '' : ` Choose ${label} to see it.`}`
      : 'Palette was not saved. Local storage may be unavailable.');
  };
  return jsxs('section', { className: 'settings-section palette-section', children: [
    jsxs('div', { className: 'palette-heading', children: [
      jsx('h3', { children: 'Color palette' }), jsx('p', { children: 'Pick a preset or make a palette just for the UniFi plugin.' }),
    ] }),
    jsxs('details', { className: 'maker', children: [
      jsx('summary', { className: 'ui-control', children: 'Theme Maker' }),
      jsxs('div', { className: 'palette-editor', children: [
        jsxs('header', { className: 'editor-head', children: [
          jsx('h3', { children: 'Theme Maker' }),
          jsxs('label', { className: 'editor-mode', children: ['Editing palette for', jsx('select', {
            'aria-label': 'Edit palette', value: mode,
            onChange: event => { if (MODES.includes(event.target.value)) setMode(event.target.value); },
            children: MODES.map(name => jsx('option', { value: name, children: `${APPEARANCE[name][0]} appearance` }, name)),
          })] }),
        ] }),
        jsxs('div', { className: 'editor-grid', children: [
          jsxs('div', { children: [
            jsx('h3', { children: 'Start from a preset' }),
            jsx('div', { className: 'presets', role: 'group', 'aria-label': 'Palette presets',
              children: Object.entries(PRESETS).map(([name, pair]) => {
                const preset = pair[mode];
                return jsxs('button', { type: 'button', className: 'ui-control', 'aria-label': name,
                  'aria-pressed': !errors.length && JSON.stringify(palette) === JSON.stringify(preset),
                  onClick: () => { setBases(current => ({ ...current, [mode]: name })); replace(preset); },
                  children: [jsx('span', { className: 'preset-dots', 'aria-hidden': true,
                    children: ['panel', 'accent', 'selected'].map(key => jsx('span', { style: { background: preset[key] } }, key)),
                  }), name],
                }, name);
              }),
            }),
            ...Object.entries(FIELDS).map(([key, name]) => jsxs('div', { className: 'palette-field', children: [
              jsx('span', { children: name }),
              jsx('input', { type: 'color', 'aria-label': `${label} ${name} swatch`,
                value: (hexColor(draft[key]) ?? preview[key]).toLowerCase(),
                onChange: event => change(key, event.target.value.toUpperCase()) }),
              jsx('input', { type: 'text', 'aria-label': `${label} ${name} hex`, 'aria-invalid': !hexColor(draft[key]),
                value: draft[key], maxLength: 7, spellCheck: false, autoComplete: 'off',
                onChange: event => change(key, event.target.value) }),
            ] }, key)),
          ] }),
          jsxs('section', { 'aria-label': 'Fictional network preview', children: [
            jsx('h3', { children: 'Network preview' }), jsx(NetworkSample, { palette: preview }),
            jsxs('div', { className: 'palette-check', 'aria-live': 'polite', children: errors.length ? [
              jsx('strong', { children: 'Not ready to apply. Preview uses the saved palette or Daybook.' }),
              jsx('ul', { children: errors.map(error => jsx('li', { children: error }, error)) }),
            ] : [jsx('strong', { children: 'Preview text passes contrast checks' }), jsx('p', { children: 'Status colors stay the same.' })] }),
          ] }),
        ] }),
        jsxs('div', { className: 'editor-actions', children: [
          jsx('p', { children: 'Applies colors only for this Desktop profile. Connection settings stay unchanged.' }),
          jsxs('div', { children: [
            jsx('button', { type: 'button', className: 'ui-control', onClick: () => replace(PRESETS[bases[mode]][mode]), children: 'Reset to preset' }),
            jsx('button', { type: 'button', className: 'ui-control apply', disabled: errors.length > 0, onClick: apply, children: `Apply to ${label}` }),
          ] }),
        ] }),
        jsx('div', { className: 'palette-result', role: 'status', children: messages[mode] }),
      ] }),
    ] }),
  ] });
}

function AppearanceControl({ choice, choose }) {
  return jsx('div', { className: 'appearance-control', role: 'group', 'aria-label': 'Appearance mode',
    children: Object.entries(APPEARANCE).map(([mode, [label, glyph]]) => jsx('button', {
      type: 'button', className: 'ui-control appearance-option', 'aria-label': label, title: label,
      'aria-pressed': mode === choice, onClick: () => choose(mode),
      children: jsx('span', { 'aria-hidden': true, className: `mode-${glyph}`,
        children: mode === 'match' || mode === 'system' ? icon(glyph, '16px') : null }),
    }, mode)),
  });
}

function SettingsPage() {
  const appearance = useAppearance();
  const light = useSavedPalette(appearance.scope, 'light');
  const dark = useSavedPalette(appearance.scope, 'dark');
  const palettes = { light, dark };
  return jsxs('section', { className: 'unifi-shell unifi-settings', 'aria-label': 'UniFi Settings', 'data-appearance': appearance.resolved,
    style: paletteStyle(palettes[appearance.resolved]), children: [
    jsx('style', { children: CHROME_CSS + MAKER_CSS }),
    jsxs('div', { className: 'settings-content', children: [
      jsxs('div', { className: 'settings-brand', children: [
        jsx('strong', { children: 'UniFi' }), jsx('span', { children: `v${PLUGIN_VERSION}` }),
      ] }),
      jsxs('header', { className: 'settings-section settings-heading settings-intro', children: [
        jsxs('div', { children: [jsx('h1', { children: 'Settings' }), jsx('p', { children: 'Set up read-only monitoring, choose what’s visible, and personalize the dashboard.' })] }),
        jsx('button', { type: 'button', className: 'ui-control', 'aria-label': 'Back to UniFi dashboard', onClick: () => host.navigate('/unifi'), children: '‹ Dashboard' }),
      ] }),
      jsxs('section', { className: 'settings-section', children: [
        jsxs('div', { className: 'settings-heading', children: [
          jsxs('div', { children: [jsx('h2', { children: 'Connections' }), jsx('p', { children: 'Edit connection details and API keys in Agent settings for this profile.' })] }),
          jsx('button', { type: 'button', className: 'ui-control', onClick: openAgentSettings, children: 'Open Agent settings' }),
        ] }),
        jsx('div', { className: 'connections-grid', children: [
          ['Site Manager · Cloud', 'Cloud summaries with a Site Manager API key.'],
          ['Local Console', 'Device and client diagnostics with a console host and Network API key.'],
          ['Privacy', 'IP addresses are off by default. Manage visibility in Agent settings. MAC addresses are never shown.'],
        ].map(([label, text]) => jsxs('div', { className: 'connection-note', children: [jsx('h3', { children: label }), jsx('p', { children: text })] }, label)) }),
      ] }),
      jsxs('section', { className: 'settings-section settings-heading', children: [
        jsxs('div', { children: [jsx('h2', { children: 'Appearance' }), jsx('p', { children: 'Match Desktop uses the Hermes Desktop theme. System follows your device.' })] }),
        jsx(AppearanceControl, appearance),
      ] }),
      jsx(ThemeMaker, { scope: appearance.scope, resolved: appearance.resolved, palettes }, appearance.scope),
    ] }),
  ] });
}

function query(name, enabled = true) {
  return useQuery({ queryKey: ['unifi', name], queryFn: loaders[name], enabled,
    refetchInterval: 60000, retry: false, staleTime: 30000 });
}

function Diagnostics({ data }) {
  const counts = data.summary || {};
  const tone = counts.critical > 0 ? 'bad' : counts.warning > 0 ? 'warn' : 'good';
  const findings = data.findings || [];
  return jsxs(React.Fragment, { children: [
    data.sources && data.sources.console === false ? jsxs('p', { className: 'notice muted', role: 'status', children: [jsx('strong', { children: 'Local console not connected. ' }), 'Add the console host and Network API key in Settings → Plugins → UniFi to check devices, clients, Wi-Fi, and ports. Only Site Manager data was checked.'] }) : null,
    jsxs('p', { className: `notice ${tone}`, role: 'status', children: [jsx('strong', { children: `${data.headline}. ` }), `${data.deviceCount ?? 0} ${data.deviceCount === 1 ? 'device' : 'devices'} and ${data.clientCount ?? 0} ${data.clientCount === 1 ? 'client' : 'clients'} checked.`] }),
    jsx('div', { className: 'cards', children: ['critical', 'warning', 'info'].map(level => jsxs('article', {
      className: `${counts[level] > 0 ? severityTone(level) : 'muted'} ${counts[level] > 0 && level !== 'info' ? 'attention' : 'healthy'}`, children: [
        jsx('h2', { children: level === 'critical' ? 'Critical problems' : level === 'warning' ? 'Warnings' : 'Notes' }), jsx('strong', { className: 'count', children: counts[level] ?? 0 }),
        jsx('p', { className: 'state', children: counts[level] > 0 ? (level === 'info' ? 'Worth knowing' : 'Needs attention') : 'None' }),
      ],
    }, level)) }),
    findings.length === 0 ? jsx('p', { className: 'empty', children: 'No findings.' }) : jsx('ol', { className: 'findings', 'aria-label': 'UniFi findings', children: findings.map(f => jsxs('li', { className: `finding ${severityTone(f.severity)}`, children: [
      jsxs('div', { className: 'finding-head', children: [jsx('span', { className: `pill ${severityTone(f.severity)}`, children: severityLabels[f.severity] || f.severity }), jsx('h3', { children: f.title })] }),
      jsx('p', { children: f.detail }),
      f.recommendation && f.recommendation !== 'No action needed.' ? jsxs('p', { className: 'action', children: [jsx('strong', { children: 'What to do: ' }), f.recommendation] }) : null,
      f.fix ? jsx('p', { className: 'fix', children: `A future version could offer to ${fixLabels[f.fix.action] || 'apply a fix'} with your approval. This version is read only; apply it in the UniFi console.` }) : null,
    ] }, f.id)) }),
  ] });
}

export function View({ tab, data }) {
  if (!data) return null;
  if (tab === 'diagnostics') return jsx(Diagnostics, { data });
  return jsxs(React.Fragment, { children: [
    data.partial ? jsxs('p', { className: 'notice warn', role: 'status', children: [jsx('strong', { children: 'Partial data. ' }), data.notice || 'Some summaries are unavailable or incomplete.'] }) : null,
    data.degraded ? jsx('p', { className: 'notice warn', role: 'status', children: 'Degraded — one or more health checks need attention.' }) : null,
    tab === 'overview' ? jsx('div', { className: 'cards', children: Object.entries(data.summaries).map(([name, summary]) => jsxs('article', {
      className: `${summaryTone(summary)} ${summary.degraded || summaryTone(summary) === 'bad' ? 'attention' : summary.partial ? 'partial' : 'healthy'}`, children: [
        jsx('h2', { children: labels[name] }), jsx('strong', { className: 'count', children: summary.count }),
        jsx('p', { className: 'state', children: `${summary.partial ? 'Partial count · ' : ''}${summaryTone(summary) === 'bad' ? `Reported ${displayValue('status', summary.status)}` : summary.degraded ? 'Needs attention' : summary.partial ? 'Incomplete reporting' : 'No reported issues'}` }),
      ],
    }, name)) }) : jsxs('section', { className: 'table-shell', 'aria-label': `UniFi ${labels[tab]}`, children: [
      jsx('div', { className: 'table-heading', children: jsx('span', { children: `${data.items.length} ${data.items.length === 1 ? 'item' : 'items'}` }) }),
      data.items.length === 0 ? jsx('p', { className: 'empty', children: 'No data available.' }) : jsx('div', { className: 'table', tabIndex: 0, role: 'region', 'aria-label': `UniFi ${labels[tab]} table, scroll to see all columns`, children: jsxs('table', { 'aria-label': `UniFi ${labels[tab]}`, children: [
        jsx('thead', { children: jsx('tr', { children: Object.entries(columns[tab]).map(([key, label]) => jsx('th', { scope: 'col', className: numericColumns.has(key) ? 'numeric' : undefined, children: label }, key)) }) }),
        jsx('tbody', { children: data.items.map((row, index) => {
          const tone = rowTone(row);
          const attention = tone === 'warn' || tone === 'bad';
          return jsx('tr', { className: attention ? `row-attention ${tone}` : undefined, children: Object.keys(columns[tab]).map((key, column) => cell(key, row[key], column === 0 && attention)) }, index);
        }) }),
      ] }) }),
    ] }),
    tab === 'overview' && Object.values(data.summaries).every(s => s.count === 0) ? jsx('p', { className: 'empty', children: 'No data available.' }) : null,
  ] });
}

function Page() {
  const [tab, setTab] = useState('overview');
  const appearance = useAppearance();
  const palette = useSavedPalette(appearance.scope, appearance.resolved);
  const health = query('health');
  const cloud = health.data?.configured === true;
  const console = health.data?.console?.configured === true;
  const available = { cloud, console, any: cloud || console };
  const configured = available.any;
  const enabled = available[sources[tab]] === true;
  const result = query(tab, enabled);
  const refresh = () => { health.refetch(); if (enabled) result.refetch(); };
  const sourceLabel = cloud && console ? 'Site Manager + console' : console ? 'Console' : 'Site Manager';
  return jsxs('main', { className: 'unifi unifi-shell', 'data-appearance': appearance.resolved, style: paletteStyle(palette), children: [
    jsx('style', { children: CSS }),
    jsx('style', { children: CHROME_CSS }),
    jsxs('header', { className: 'topbar', children: [
      jsxs('div', { className: 'brand', children: [
        jsx('span', { className: 'brand-icon', 'aria-hidden': true, children: icon(PRODUCT_ICON, '20px') }),
        jsxs('div', { className: 'brand-title', children: [
          jsx('h1', { children: 'Hermes for UniFi' }), jsx('span', { className: 'app-version', children: `v${PLUGIN_VERSION}` }),
        ] }),
      ] }),
      jsxs('div', { className: 'top-actions', children: [
      jsxs('div', { className: 'connection', children: [jsx(StatusDot, { tone: health.error || result.error ? 'bad' : result.data?.data?.degraded || result.data?.data?.summary?.critical > 0 ? 'warn' : configured ? 'good' : 'muted' }), jsx('span', { children: health.error ? 'Connection unavailable' : health.isLoading ? 'Checking configuration' : !configured ? 'Not configured' : result.error ? `${sourceLabel} · refresh failed` : result.data ? `${sourceLabel} · data loaded` : `${sourceLabel} · configured` })] }),
      jsx('span', { className: 'readonly muted', children: 'Read only' }),
      jsx(AppearanceControl, appearance),
      jsx('div', { className: 'refresh', children: jsx(Button, { onClick: refresh, disabled: health.isFetching || result.isFetching, children: 'Refresh' }) }),
      typeof ctx.registerSettingsPage === 'function' ? jsx('button', {
        type: 'button', className: 'ui-control settings-gear', 'aria-label': 'UniFi Settings', title: 'UniFi Settings',
        onClick: openSettings, children: icon('settings-gear', '18px'),
      }) : null,
      ] }),
    ] }),
    jsxs('div', { className: 'unifi-body', children: [
    jsx('nav', { 'aria-label': 'UniFi views', children: Object.entries(labels).map(([name, label]) => jsx(Button, { onClick: () => setTab(name), 'aria-pressed': tab === name, children: label }, name)) }),
    jsxs('div', { className: 'view-heading', children: [jsx('h2', { children: labels[tab] }), jsx('p', { children: descriptions[tab] })] }),
    health.isLoading || (enabled && result.isLoading) ? jsxs('p', { role: 'status', children: [jsx(GlyphSpinner, {}), ' Loading UniFi data…'] }) : null,
    !health.isLoading && !health.error && !configured ? jsx('p', { children: 'Unconfigured. Open Settings → Plugins → UniFi and save a profile-scoped API key, or the console host and Network API key for local diagnostics.' }) : null,
    !health.isLoading && !health.error && configured && !enabled ? jsx('p', { className: 'notice muted', role: 'status', children: sources[tab] === 'console' ? 'This view needs the local console. Add the console host and Network API key in Settings → Plugins → UniFi.' : 'This view needs the Site Manager API key. Add it in Settings → Plugins → UniFi.' }) : null,
    health.error || (enabled && result.error) ? jsx(ErrorState, { title: 'UniFi data unavailable', description: health.error ? 'Check that the Agent/backend part is installed and enabled on the connected backend.' : result.data ? 'Degraded: refresh failed. Previously loaded data is shown.' : result.error?.message || 'Check configuration or retry later.', onRetry: refresh }) : null,
    enabled ? jsx(View, { tab, data: result.data?.data }) : null,
    jsxs('footer', { children: [jsx('p', { className: 'disclaimer', children: 'Unofficial integration. UniFi is a trademark of Ubiquiti Inc. This project is not affiliated with/endorsed by Ubiquiti.' }), jsx('h2', { children: 'Data notes' }), jsx('ul', { children: ['Refreshes every 60 seconds', 'Latest ISP period only', 'Unknown means not reported', 'Site / host numbers are temporary and may change after refresh', 'Device and client handles are temporary labels, not identities', 'Diagnostics describe fixes but never apply them'].map(note => jsx('li', { children: note }, note)) })] }),
    ] }),
  ] });
}

export default {
  id: 'unifi', name: 'UniFi', defaultEnabled: false,
  register(context) {
    ctx = context;
    preferences = createPreferences(context.storage);
    context.registerSettingsPage?.({ id: 'settings', title: 'UniFi', icon: PRODUCT_ICON, render: () => jsx(SettingsPage, {}) });
    context.registerMany([
      { id: 'page', area: ROUTES_AREA, data: { path: '/unifi' }, render: () => jsx(Page, {}) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: '/unifi', label: 'UniFi', codicon: PRODUCT_ICON } },
      { id: 'open', area: PALETTE_AREA, data: { id: 'unifi.open', label: 'Open UniFi', keywords: ['network', 'sites', 'diagnostics', 'clients'], run: () => host.navigate(ROUTE) } },
    ]);
  },
};
