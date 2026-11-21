'use strict';
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const vm = require('node:vm');

const ROOT = resolve(__dirname, '../..');
const payloads = require('../fixtures/preview.json');
const routes = new Map([
  ['/health', 'health'], ['/overview', 'overview'], ['/diagnostics', 'diagnostics'],
  ['/sites', 'sites'], ['/devices', 'devices'], ['/isp', 'isp'], ['/console/clients', 'clients'],
]);

async function load(options = {}) {
  const registrations = [], settings = [], navigations = [], queries = [], calls = [];
  const writes = [], values = options.values ?? new Map();
  const profileListeners = new Set(), mediaListeners = new Set();
  const connectionListeners = new Set();
  let connectionId = options.connectionId ?? 'local';
  let profile = options.profile ?? 'default', hooks, cursor;
  function forbidden(name) { return () => assert.fail(`Unexpected host access: ${name}`); }
  const media = {
    matches: false,
    addEventListener(event, fn) { assert.equal(event, 'change'); mediaListeners.add(fn); },
    removeEventListener(event, fn) { assert.equal(event, 'change'); mediaListeners.delete(fn); },
  };
  const Fragment = Symbol('Fragment');
  const jsx = (type, props, key) => ({ type, props, key });
  const modules = {
    react: {
      default: { Fragment },
      useState(initial) {
        const slots = hooks, index = cursor++;
        if (!(index in slots)) slots[index] = typeof initial === 'function' ? initial() : initial;
        return [slots[index], value => { slots[index] = typeof value === 'function' ? value(slots[index]) : value; }];
      },
      useSyncExternalStore(subscribe, get) {
        const index = cursor++;
        if (hooks[index]?.subscribe !== subscribe) {
          hooks[index]?.dispose();
          const slot = { subscribe, get };
          slot.dispose = subscribe(() => { slot.notified = true; });
          hooks[index] = slot;
        }
        return get();
      },
    },
    'react/jsx-runtime': { jsx, jsxs: jsx },
    '@hermes/plugin-sdk': {
      Button: props => jsx('button', { type: 'button', ...props }),
      Codicon: ({ name }) => jsx('i', { 'data-icon': name }),
      ErrorState: props => jsx('p', { children: props.description }),
      GlyphSpinner: () => jsx('span', { children: 'Loading' }),
      StatusDot: ({ tone }) => jsx('span', { 'data-tone': tone }),
      ROUTES_AREA: 'routes', SIDEBAR_NAV_AREA: 'nav', PALETTE_AREA: 'palette',
      ...(options.legacy ? {} : {
        pluginSettingsHref: id => `/settings?${new URLSearchParams({ tab: 'plugins', plugin: id })}`,
      }),
      host: {
        navigate: href => navigations.push(href),
        state: {
          profile: {
            get: () => profile,
            subscribe(fn) { profileListeners.add(fn); return () => profileListeners.delete(fn); },
          },
          ...(options.noConnectionState ? {} : { connectionId: {
            get: () => connectionId,
            subscribe(fn) {
              connectionListeners.add(fn);
              fn(connectionId);
              return () => connectionListeners.delete(fn);
            },
          } }),
        },
        settings: new Proxy({}, { get: forbidden('host.settings') }),
        request: forbidden('host.request'),
      },
      useQuery(query) {
        queries.push(query);
        const enabled = query.enabled !== false;
        return { data: enabled ? query.queryFn() : undefined,
          refetch() { if (enabled) query.queryFn(); } };
      },
    },
  };
  const context = vm.createContext({
    URLSearchParams, fetch: forbidden('fetch'),
    document: new Proxy({}, { get: forbidden('document') }),
    window: {
      fetch: forbidden('window.fetch'),
      localStorage: new Proxy({}, { get: forbidden('window.localStorage') }),
      matchMedia(query) { assert.equal(query, '(prefers-color-scheme: dark)'); return media; },
    },
  });
  const plugin = new vm.SourceTextModule(readFileSync(resolve(ROOT, 'desktop/plugin.js'), 'utf8'), { context });
  await plugin.link(name => {
    assert.ok(Object.hasOwn(modules, name), `Unexpected import: ${name}`);
    const entries = Object.entries(modules[name]);
    return new vm.SyntheticModule(entries.map(([key]) => key), function () {
      for (const [key, value] of entries) this.setExport(key, value);
    }, { context });
  });
  await plugin.evaluate();
  plugin.namespace.default.register({
    registerMany: items => registrations.push(...items),
    ...(options.legacy ? {} : { registerSettingsPage: page => settings.push(page) }),
    rest(path) {
      assert.ok(routes.has(path), `Unexpected REST route: ${path}`);
      calls.push(path);
      return path === '/health' ? options.health ?? { configured: true, console: { configured: true } }
        : { data: payloads[routes.get(path)] };
    },
    storage: {
      get(key) { return options.readFailure ? forbidden('storage.get')() : values.get(key); },
      set(key, value) { writes.push([key, value]); if (!options.blockWrites) values.set(key, value); },
    },
  });

  // Traverse component output only; no HTML renderer or browser. Key changes
  // replace a component's state and dispose its subscriptions, as React does.
  function mount(contribution) {
    let previous = new Map();
    const dispose = slots => slots.forEach(slot => slot?.dispose?.());
    return {
      render() {
        assert.ok(contribution, 'Missing registered page');
        const current = new Map(), elements = [], words = [];
        function walk(node, path) {
          if (Array.isArray(node)) return node.forEach((child, i) => walk(child, `${path}/${i}`));
          if (typeof node === 'string' || typeof node === 'number') return words.push(node);
          if (!node || typeof node !== 'object') return;
          const { type, props, key } = node;
          if (typeof type === 'function') {
            const id = `${path}:${type.name}:${key ?? ''}`;
            hooks = previous.get(id) ?? [];
            cursor = 0;
            current.set(id, hooks);
            return walk(type(props), `${id}/content`);
          }
          if (type !== Fragment) elements.push(node);
          if (type !== 'style') walk(props.children, `${path}/children`);
        }
        walk(contribution.render(), 'root');
        for (const [key, slots] of previous) if (!current.has(key)) dispose(slots);
        previous = current;
        return {
          elements, text: words.join(' '),
          find: (type, label) => elements.find(node => node.type === type &&
            (node.props['aria-label'] ?? node.props.children) === label)?.props,
        };
      },
      unmount() { previous.forEach(dispose); previous.clear(); },
    };
  }
  return {
    registrations, settings, navigations, queries, calls, writes, values,
    dashboard: () => mount(registrations.find(item => item.id === 'page')),
    settingsPage: () => mount(settings[0]),
    switchProfile(next) { profile = next; profileListeners.forEach(fn => fn(next)); },
    switchConnection(next) { connectionId = next; connectionListeners.forEach(fn => fn(next)); },
    connectionListenerCount: () => connectionListeners.size,
    setDark(next) { media.matches = next; mediaListeners.forEach(fn => fn({ matches: next })); },
    listenerCounts: () => [profileListeners.size, mediaListeners.size],
  };
}

function button(view, name) {
  const props = view.find('button', name);
  assert.ok(props, `Missing native button: ${name}`);
  assert.equal(props.type, 'button');
  assert.ok(props.tabIndex == null || props.tabIndex >= 0);
  return props;
}

module.exports = { load, button, ROOT };
