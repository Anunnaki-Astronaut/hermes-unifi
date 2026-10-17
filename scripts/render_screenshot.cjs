#!/usr/bin/env node
// Static HTML preview of the real component. No browser, network, or remote imports.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const tab = process.argv[2] || 'overview';
if (!['overview', 'sites', 'devices', 'isp'].includes(tab)) throw new Error('Unknown view');
const payloads = JSON.parse(fs.readFileSync(path.join(root, 'tests/fixtures/preview.json'), 'utf8'));
const element = (type, props) => ({ type, props: props || {} });
const escape = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
function render(node) {
  if (node == null || typeof node === 'boolean') return '';
  if (Array.isArray(node)) return node.map(render).join('');
  if (typeof node !== 'object') return escape(node);
  if (typeof node.type === 'function') return render(node.type(node.props));
  if (node.type === 'fragment') return render(node.props.children);
  // Local authored CSS is raw text in HTML, not an escaped text node.
  if (node.type === 'style') return `<style>${node.props.children}</style>`;
  const attrs = Object.entries(node.props).filter(([k,v]) => k !== 'children' && !k.startsWith('on') && v != null && (v !== false || k.startsWith('aria-'))).map(([k,v]) => ` ${k === 'className' ? 'class' : k === 'tabIndex' ? 'tabindex' : k}="${escape(v)}"`).join('');
  return `<${node.type}${attrs}>${render(node.props.children)}</${node.type}>`;
}
(async () => {
  const context = vm.createContext({}); // No fetch, timers, require, process, or sockets.
  const modules = {
    react: { default: { Fragment: 'fragment' }, useState: () => [tab, () => {}] },
    'react/jsx-runtime': { jsx: element, jsxs: element },
    '@hermes/plugin-sdk': {
      Button: props => element('button', props), ErrorState: props => element('p', { children: props.description }),
      GlyphSpinner: () => element('span', { children: 'Loading' }), StatusDot: () => element('span', { children: '●' }),
      host: { navigate() {} }, ROUTES_AREA: 'routes', SIDEBAR_NAV_AREA: 'nav', PALETTE_AREA: 'palette',
      useQuery: options => ({ data: options.queryKey[1] === 'health' ? { configured: true } : { data: payloads[options.queryKey[1]] }, refetch() {}, isLoading: false, isFetching: false }),
    },
  };
  const plugin = new vm.SourceTextModule(fs.readFileSync(path.join(root, 'desktop/plugin.js'), 'utf8'), { context });
  await plugin.link(name => {
    if (!Object.hasOwn(modules, name)) throw new Error('Unexpected import');
    return new vm.SyntheticModule(Object.keys(modules[name]), function () {
      for (const [key, value] of Object.entries(modules[name])) this.setExport(key, value);
    }, { context });
  });
  await plugin.evaluate();
  let page;
  plugin.namespace.default.register({ rest() { throw new Error('Network forbidden'); }, registerMany(entries) { page = entries.find(e => e.area === 'routes').render; } });
  const html = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>UniFi synthetic preview</title><style>:root{--ui-text-primary:#e7edf5;--ui-text-secondary:#9daec2;--ui-bg-card:#182332;--ui-stroke-secondary:#344256;--ui-yellow:#e4b450}body{background:#0e1723;font-family:system-ui;margin:0}button{background:#23354b;color:#e7edf5;padding:10px 16px;border:1px solid #344256;border-radius:6px}</style>' + render(page()) + '</html>\n';
  const output = path.resolve(process.argv[3] || path.join(root, `docs/screenshots/${tab}.html`));
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, html);
  console.log(`Rendered synthetic ${tab} preview`);
})().catch(error => { console.error(error); process.exitCode = 1; });
