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
  sites: { name: 'Name', description: 'Description', timezone: 'Timezone', totalDevices: 'Devices', offlineDevices: 'Offline', pendingUpdates: 'Updates', wanUptime: 'WAN uptime (%)' },
  devices: { name: 'Name', model: 'Model', productLine: 'Product line', status: 'Status', version: 'Version', firmwareStatus: 'Firmware', updateAvailable: 'Available version' },
  isp: { label: 'Site / host', metricTime: 'Latest period (UTC)', ispName: 'ISP', avgLatency: 'Average latency', maxLatency: 'Maximum latency', download_kbps: 'Download (kbps)', upload_kbps: 'Upload (kbps)', downtime: 'Downtime', packetLoss: 'Packet loss', uptime: 'Uptime' },
};
const CSS = `.unifi{padding:24px;color:var(--ui-text-primary);max-width:1400px;margin:auto}.unifi header,.unifi nav{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:24px}.unifi h1{margin:0}.unifi p,.unifi footer{color:var(--ui-text-secondary)}.unifi .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:16px}.unifi article{padding:24px;border:1px solid var(--ui-stroke-secondary);border-radius:12px;background:var(--ui-bg-card)}.unifi strong{font-size:32px}.unifi .table{overflow:auto}.unifi table{width:100%;border-collapse:collapse}.unifi th,.unifi td{text-align:left;padding:14px;border-bottom:1px solid var(--ui-stroke-secondary)}.unifi .notice{padding:16px;border:1px solid var(--ui-yellow);border-radius:8px;margin:16px 0}.unifi footer{margin-top:24px;font-size:12px}`;

function query(name, enabled = true) {
  return useQuery({ queryKey: ['unifi', name], queryFn: loaders[name], enabled,
    refetchInterval: 60000, retry: false, staleTime: 30000 });
}

export function View({ tab, data }) {
  if (!data) return null;
  return jsxs(React.Fragment, { children: [
    data.partial ? jsx('p', { className: 'notice', role: 'status', children: data.notice || 'Partial error: some summaries are unavailable or incomplete.' }) : null,
    data.degraded ? jsx('p', { className: 'notice', role: 'status', children: 'Degraded — one or more health checks need attention.' }) : null,
    tab === 'overview' ? jsx('div', { className: 'cards', children: Object.entries(data.summaries).map(([name, summary]) => jsxs('article', { children: [
      jsx('h2', { children: labels[name] }), jsx('strong', { children: summary.count }),
      jsx('p', { children: `${summary.partial ? 'Partial count · ' : ''}${summary.degraded ? 'Needs attention' : 'No reported issues'}` }),
    ] }, name)) }) : data.items.length === 0 ? jsx('p', { children: 'No data available.' }) : jsx('div', { className: 'table', children: jsxs('table', { 'aria-label': `UniFi ${labels[tab]}`, children: [
      jsx('thead', { children: jsx('tr', { children: Object.values(columns[tab]).map(label => jsx('th', { scope: 'col', children: label }, label)) }) }),
      jsx('tbody', { children: data.items.map((row, index) => jsx('tr', { children: Object.keys(columns[tab]).map(key => jsx('td', { children: row[key] ?? 'Unknown' }, key)) }, index)) }),
    ] }) }),
    tab === 'overview' && Object.values(data.summaries).every(s => s.count === 0) ? jsx('p', { children: 'No data available.' }) : null,
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
    jsxs('header', { children: [jsx('h1', { children: 'UniFi' }), jsx(StatusDot, { tone: result.error || result.data?.data?.degraded ? 'warn' : configured ? 'good' : 'muted' }), jsx('span', { children: configured ? 'Read-only Site Manager' : 'Not configured' }), jsx(Button, { onClick: refresh, disabled: health.isFetching || result.isFetching, children: 'Refresh' })] }),
    jsx('nav', { 'aria-label': 'UniFi views', children: Object.entries(labels).map(([name, label]) => jsx(Button, { onClick: () => setTab(name), 'aria-pressed': tab === name, children: label }, name)) }),
    health.isLoading || (configured && result.isLoading) ? jsxs('p', { role: 'status', children: [jsx(GlyphSpinner, {}), ' Loading UniFi data…'] }) : null,
    !health.isLoading && !health.error && !configured ? jsx('p', { children: 'Unconfigured. Open Settings → Plugins → UniFi and save a profile-scoped API key.' }) : null,
    health.error || (configured && result.error) ? jsx(ErrorState, { title: 'UniFi data unavailable', description: result.data ? 'Degraded: refresh failed. Previously loaded data is shown.' : 'Check configuration or retry later.', onRetry: refresh }) : null,
    configured ? jsx(View, { tab, data: result.data?.data }) : null,
    jsx('footer', { children: 'Refreshes every 60 seconds · Latest ISP period only · Unknown means not reported · Site / host labels are temporary row numbers' }),
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
