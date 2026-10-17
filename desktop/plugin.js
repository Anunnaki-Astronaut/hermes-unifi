import React, { useState } from 'react';
import { jsx, jsxs } from 'react/jsx-runtime';
import { Button, ErrorState, GlyphSpinner, StatusDot, useQuery, host, ROUTES_AREA, SIDEBAR_NAV_AREA, PALETTE_AREA } from '@hermes/plugin-sdk';

let ctx;
const loaders = {
  health: () => ctx.rest('/health'),
  overview: () => ctx.rest('/overview'),
  sites: () => ctx.rest('/sites'),
  devices: () => ctx.rest('/devices'),
  isp: () => ctx.rest('/isp'),
};
const labels = { overview: 'Overview', sites: 'Sites', devices: 'Devices', isp: 'ISP Health' };
const columns = {
  sites: { name: 'Name', description: 'Description', timezone: 'Timezone', totalDevices: 'Devices', offlineDevices: 'Offline', pendingUpdates: 'Updates', wanUptime: 'WAN uptime' },
  devices: { name: 'Name', model: 'Model', productLine: 'Product line', status: 'Status', version: 'Version', firmwareStatus: 'Firmware', updateAvailable: 'Available version' },
  isp: { label: 'Site / host', metricTime: 'Latest period (UTC)', ispName: 'ISP', avgLatency: 'Average latency', maxLatency: 'Maximum latency', download_kbps: 'Download (kbps)', upload_kbps: 'Upload (kbps)', downtime: 'Downtime', packetLoss: 'Packet loss', uptime: 'Uptime' },
};
const descriptions = {
  overview: 'Reported counts and health across sites, devices, and ISP records.',
  sites: 'Device counts, pending updates, and WAN uptime by site.',
  devices: 'Reported device status, installed versions, and firmware availability.',
  isp: 'ISP metrics for the latest reported period at each site / host.',
};
const numericColumns = new Set(['totalDevices', 'offlineDevices', 'pendingUpdates', 'wanUptime', 'avgLatency', 'maxLatency', 'download_kbps', 'upload_kbps', 'downtime', 'packetLoss', 'uptime']);
const enumLabels = { upToDate: 'Up to date', updateAvailable: 'Update available', online: 'Online', offline: 'Offline', connected: 'Connected', disconnected: 'Disconnected', pending: 'Pending', updating: 'Updating', unknown: 'Unknown' };
function displayValue(key, value) {
  if (value == null || (typeof value === 'string' && value.trim() === '')) return '—';
  if (key !== 'status' && key !== 'firmwareStatus') return value;
  if (Object.hasOwn(enumLabels, value)) return enumLabels[value];
  return typeof value === 'string' && /^[a-z]+$/.test(value) ? value[0].toUpperCase() + value.slice(1) : value;
}
function needsAttention(row) {
  return row.offlineDevices > 0 || row.pendingUpdates > 0 || (typeof row.wanUptime === 'number' && row.wanUptime < 100)
    || (row.status != null && row.status !== 'online' && row.status !== 'unknown')
    || row.packetLoss > 0 || row.downtime > 0;
}
function cell(key, value, rowAttention = false) {
  const label = displayValue(key, value);
  const muted = label === '—' || label === 'Unknown';
  const pill = !muted && (key === 'status' || key === 'firmwareStatus');
  const attention = ['offline', 'disconnected', 'updateAvailable'].includes(value);
  return jsxs('td', { className: numericColumns.has(key) ? 'numeric' : undefined, children: [jsx('span', {
    className: muted ? 'muted' : pill ? `pill ${attention ? 'attention' : ''}` : undefined, children: label,
  }), rowAttention ? jsx('span', { className: 'row-note', children: 'Needs attention' }) : null] }, key);
}
const CSS = `
.unifi{padding:24px;color:var(--ui-text-primary);max-width:1400px;min-width:0;box-sizing:border-box;margin:auto}
.unifi *{box-sizing:border-box}.unifi h1,.unifi h2,.unifi p{margin:0}
.unifi .topbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:20px}
.unifi .brand{display:flex;align-items:center;gap:10px}.unifi h1{font-size:20px;line-height:1.3}
.unifi .mark{width:24px;height:28px;border:4px solid var(--ui-yellow);border-top:0;border-radius:0 0 12px 12px;position:relative}
.unifi .mark:after{content:'';position:absolute;right:-4px;top:0;width:4px;height:7px;background:var(--ui-bg-card)}
.unifi .connection{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--ui-text-secondary)}
.unifi .readonly,.unifi .pill{display:inline-block;border:1px solid var(--ui-stroke-secondary);border-radius:5px;padding:3px 7px;font-size:12px;line-height:1.4;white-space:nowrap}
.unifi .readonly{color:var(--ui-text-secondary)}.unifi .refresh{margin-left:auto}
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
.unifi .healthy .state:before{background:currentColor}.unifi .partial .state:before{border-radius:0}.unifi .attention .state:before{border-radius:0;transform:rotate(45deg)}
.unifi .attention,.unifi .partial{color:var(--ui-yellow)}.unifi article.attention,.unifi article.partial{color:var(--ui-text-primary);border-top-color:var(--ui-yellow)}.unifi article.attention .state,.unifi article.partial .state{color:var(--ui-yellow)}
.unifi .table-shell{min-width:0;border:1px solid var(--ui-stroke-secondary);border-radius:8px;background:var(--ui-bg-card);overflow:hidden}
.unifi .table-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 16px;border-bottom:1px solid var(--ui-stroke-secondary)}.unifi .table-heading span{font-size:12px;color:var(--ui-text-secondary);font-variant-numeric:tabular-nums}
.unifi .table{overflow:auto;max-height:60vh;isolation:isolate}.unifi .table:focus-visible{outline-offset:-3px}
.unifi table{width:100%;border-collapse:separate;border-spacing:0;font-size:13px}
.unifi th,.unifi td{text-align:left;padding:12px 16px;border-bottom:1px solid var(--ui-stroke-secondary);white-space:nowrap}
.unifi th{position:sticky;top:0;z-index:1;background:var(--ui-bg-card);font-size:12px;font-weight:600;color:var(--ui-text-secondary)}
.unifi .numeric{text-align:right;font-variant-numeric:tabular-nums}.unifi tbody tr:last-child td{border-bottom:0}
.unifi tbody tr:hover{background:var(--ui-stroke-secondary)}.unifi tr.row-attention td:first-child{border-left:3px solid var(--ui-yellow);padding-left:13px}
.unifi .row-note{display:block;margin-top:4px;font-size:11px;color:var(--ui-yellow)}.unifi .muted{color:var(--ui-text-secondary)}
.unifi .notice{padding:12px 14px;border:1px solid var(--ui-stroke-secondary);border-left:3px solid var(--ui-yellow);border-radius:5px;margin:0 0 16px;font-size:13px;line-height:1.6}
.unifi .empty{padding:16px;color:var(--ui-text-secondary)}
.unifi footer{margin-top:24px;padding-top:16px;border-top:1px solid var(--ui-stroke-secondary);font-size:12px;color:var(--ui-text-secondary)}
.unifi footer h2{font-size:12px;color:var(--ui-text-primary);font-weight:600}.unifi footer ul{display:flex;flex-wrap:wrap;gap:8px 28px;padding-left:16px;margin:10px 0 0;line-height:1.5}
@media(max-width:800px){.unifi{padding:16px}.unifi .connection{order:3;flex-basis:100%}.unifi .cards{gap:8px}.unifi article{padding:12px}.unifi nav{width:100%}.unifi nav button{flex:1;padding:7px 10px}}
@media(max-width:520px){.unifi .cards{grid-template-columns:1fr}.unifi footer ul{display:grid;gap:6px}.unifi .readonly{font-size:11px}}
`;

function query(name, enabled = true) {
  return useQuery({ queryKey: ['unifi', name], queryFn: loaders[name], enabled,
    refetchInterval: 60000, retry: false, staleTime: 30000 });
}

export function View({ tab, data }) {
  if (!data) return null;
  return jsxs(React.Fragment, { children: [
    data.partial ? jsxs('p', { className: 'notice', role: 'status', children: [jsx('strong', { children: 'Partial data. ' }), data.notice || 'Some summaries are unavailable or incomplete.'] }) : null,
    data.degraded ? jsx('p', { className: 'notice', role: 'status', children: 'Degraded — one or more health checks need attention.' }) : null,
    tab === 'overview' ? jsx('div', { className: 'cards', children: Object.entries(data.summaries).map(([name, summary]) => jsxs('article', {
      className: summary.degraded ? 'attention' : summary.partial ? 'partial' : 'healthy', children: [
        jsx('h2', { children: labels[name] }), jsx('strong', { className: 'count', children: summary.count }),
        jsx('p', { className: 'state', children: `${summary.partial ? 'Partial count · ' : ''}${summary.degraded ? 'Needs attention' : summary.partial ? 'Incomplete reporting' : 'No reported issues'}` }),
      ],
    }, name)) }) : jsxs('section', { className: 'table-shell', 'aria-label': `UniFi ${labels[tab]}`, children: [
      jsx('div', { className: 'table-heading', children: jsx('span', { children: `${data.items.length} ${data.items.length === 1 ? 'item' : 'items'}` }) }),
      data.items.length === 0 ? jsx('p', { className: 'empty', children: 'No data available.' }) : jsx('div', { className: 'table', tabIndex: 0, role: 'region', 'aria-label': `UniFi ${labels[tab]} table, scroll to see all columns`, children: jsxs('table', { 'aria-label': `UniFi ${labels[tab]}`, children: [
        jsx('thead', { children: jsx('tr', { children: Object.entries(columns[tab]).map(([key, label]) => jsx('th', { scope: 'col', className: numericColumns.has(key) ? 'numeric' : undefined, children: label }, key)) }) }),
        jsx('tbody', { children: data.items.map((row, index) => {
          const attention = needsAttention(row);
          return jsx('tr', { className: attention ? 'row-attention' : undefined, children: Object.keys(columns[tab]).map((key, column) => cell(key, row[key], column === 0 && attention)) }, index);
        }) }),
      ] }) }),
    ] }),
    tab === 'overview' && Object.values(data.summaries).every(s => s.count === 0) ? jsx('p', { className: 'empty', children: 'No data available.' }) : null,
  ] });
}

function Page() {
  const [tab, setTab] = useState('overview');
  const health = query('health');
  const configured = health.data?.configured === true;
  const result = query(tab, configured);
  const refresh = () => { health.refetch(); if (configured) result.refetch(); };
  return jsxs('main', { className: 'unifi', children: [
    jsx('style', { children: CSS }),
    jsxs('header', { className: 'topbar', children: [
      jsxs('div', { className: 'brand', children: [jsx('span', { className: 'mark', 'aria-hidden': true }), jsx('h1', { children: 'UniFi' })] }),
      jsxs('div', { className: 'connection', children: [jsx(StatusDot, { tone: health.error || result.error || result.data?.data?.degraded ? 'warn' : configured ? 'good' : 'muted' }), jsx('span', { children: health.error ? 'Connection unavailable' : health.isLoading ? 'Checking configuration' : !configured ? 'Not configured' : result.error ? 'Site Manager · refresh failed' : result.data ? 'Site Manager · data loaded' : 'Site Manager · configured' })] }),
      jsx('span', { className: 'readonly', children: 'Read only' }),
      jsx('div', { className: 'refresh', children: jsx(Button, { onClick: refresh, disabled: health.isFetching || result.isFetching, children: 'Refresh' }) }),
    ] }),
    jsx('nav', { 'aria-label': 'UniFi views', children: Object.entries(labels).map(([name, label]) => jsx(Button, { onClick: () => setTab(name), 'aria-pressed': tab === name, children: label }, name)) }),
    jsxs('div', { className: 'view-heading', children: [jsx('h2', { children: labels[tab] }), jsx('p', { children: descriptions[tab] })] }),
    health.isLoading || (configured && result.isLoading) ? jsxs('p', { role: 'status', children: [jsx(GlyphSpinner, {}), ' Loading UniFi data…'] }) : null,
    !health.isLoading && !health.error && !configured ? jsx('p', { children: 'Unconfigured. Open Settings → Plugins → UniFi and save a profile-scoped API key.' }) : null,
    health.error || (configured && result.error) ? jsx(ErrorState, { title: 'UniFi data unavailable', description: result.data ? 'Degraded: refresh failed. Previously loaded data is shown.' : 'Check configuration or retry later.', onRetry: refresh }) : null,
    configured ? jsx(View, { tab, data: result.data?.data }) : null,
    jsxs('footer', { children: [jsx('h2', { children: 'Data notes' }), jsx('ul', { children: ['Refreshes every 60 seconds', 'Latest ISP period only', 'Unknown means not reported', 'Site / host labels are temporary row numbers'].map(note => jsx('li', { children: note }, note)) })] }),
  ] });
}

export default {
  id: 'unifi', name: 'UniFi', defaultEnabled: false,
  register(context) {
    ctx = context;
    context.registerMany([
      { id: 'page', area: ROUTES_AREA, data: { path: '/unifi' }, render: () => jsx(Page, {}) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: '/unifi', label: 'UniFi', codicon: 'server' } },
      { id: 'open', area: PALETTE_AREA, data: { id: 'unifi.open', label: 'Open UniFi', keywords: ['network', 'sites'], run: () => host.navigate('/unifi') } },
    ]);
  },
};
