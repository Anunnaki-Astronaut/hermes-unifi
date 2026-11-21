'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { load, button, ROOT } = require('./harness.cjs');

test('dashboard masthead and sidebar share the native target glyph; both surfaces show manifest version', async () => {
  const app = await load();
  const dashboard = app.dashboard().render();
  const settings = app.settingsPage().render();
  const version = /^version: (.+)$/m.exec(readFileSync(resolve(ROOT, 'plugin.yaml'), 'utf8'))[1];
  const nav = app.registrations.find(item => item.area === 'nav').data;
  assert.deepEqual([nav.label, nav.codicon], ['UniFi', 'target']);
  assert.ok(dashboard.elements.some(node => node.type === 'i' && node.props['data-icon'] === nav.codicon));
  const title = dashboard.elements.find(node => node.props.className === 'brand-title');
  assert.deepEqual(Array.from(title.props.children, node => node.props.children), ['Hermes for UniFi', `v${version}`]);
  assert.ok(settings.text.includes(`v${version}`));
  const gear = button(dashboard, 'UniFi Settings');
  assert.equal(gear.title, 'UniFi Settings');
  assert.equal(gear.children.props.name, 'settings-gear');
});

test('native Settings opens before configuration, delegates Agent settings using the profile at click, and returns', async () => {
  const app = await load({ health: { configured: false } });
  button(app.dashboard().render(), 'UniFi Settings').onClick();
  assert.deepEqual(app.navigations, ['/settings?tab=plugins&plugin=unifi']);
  assert.equal(app.settings.length, 1);
  assert.equal(app.settings[0].title, 'UniFi');
  assert.deepEqual(app.calls, ['/health']);
  app.calls.length = app.queries.length = 0;
  const settings = app.settingsPage().render();
  for (const copy of ['Connections', 'Site Manager · Cloud', 'Local Console', 'Privacy', 'IP addresses are off by default', 'MAC addresses are never shown']) {
    assert.ok(settings.text.includes(copy), copy);
  }
  assert.ok(!settings.elements.some(node => ['form', 'textarea'].includes(node.type)));
  const openAgent = button(settings, 'Open Agent settings').onClick;
  app.switchProfile('office & bench/2');
  openAgent();
  button(settings, 'Back to UniFi dashboard').onClick();
  assert.deepEqual(app.navigations.slice(1), ['/settings?tab=plugins&agent=unifi&profile=office+%26+bench%2F2', '/unifi']);
  assert.deepEqual(app.calls, []);
  assert.deepEqual(app.queries, []);
});

test('legacy hosts without registrar or route helper do not show a dead gear', async () => {
  const app = await load({ legacy: true });
  const dashboard = app.dashboard().render();
  assert.equal(dashboard.find('button', 'UniFi Settings'), undefined);
  button(dashboard, 'Refresh');
  assert.deepEqual(app.settings, []);
});

test('dashboard maintains query keys, timing, source gating, Refresh and read-only copy', async () => {
  const app = await load();
  const page = app.dashboard();
  for (const tab of ['Overview', 'Diagnostics', 'Sites', 'Devices', 'ISP Health', 'Clients']) {
    button(page.render(), tab).onClick();
    const current = page.render();
    assert.equal(button(current, tab)['aria-pressed'], true);
    assert.match(current.text, /Read only/);
    assert.match(current.text, /Refreshes every 60 seconds/);
    assert.match(current.text, /not affiliated with\/endorsed by Ubiquiti/);
  }
  app.calls.length = 0;
  button(page.render(), 'Refresh').onClick();
  assert.deepEqual(app.calls, ['/health', '/console/clients', '/health', '/console/clients']);
  assert.deepEqual([...new Set(app.queries.map(q => q.queryKey.join('/')))],
    ['unifi/health', 'unifi/overview', 'unifi/diagnostics', 'unifi/sites', 'unifi/devices', 'unifi/isp', 'unifi/clients']);
  assert.ok(app.queries.every(q => q.refetchInterval === 60000 && q.staleTime === 30000 && q.retry === false));
  const local = await load({ health: { configured: false, console: { configured: true } } });
  const localPage = local.dashboard();
  assert.match(localPage.render().text, /This view needs the Site Manager API key/);
  assert.deepEqual(local.calls, ['/health']);
  button(localPage.render(), 'Diagnostics').onClick();
  localPage.render();
  assert.deepEqual(local.calls.slice(-2), ['/health', '/diagnostics']);
});

const modes = ['Match Desktop', 'System', 'Light', 'Dark'];
const appearance = view => view.elements[0].props['data-appearance'];

test('selected dashboard tabs override the host pressed background with the plugin surface', async () => {
  const app = await load();
  const view = app.dashboard().render();
  const css = view.elements.filter(node => node.type === 'style').map(node => node.props.children).join('\n');
  const selectedTab = /\.unifi-shell\s+\.unifi-body\s+nav\s+button\[aria-pressed=true\]\s*\{([^}]*)\}/.exec(css);
  assert.ok(selectedTab, 'selected dashboard tab rule must be rendered');
  assert.match(selectedTab[1], /(?:^|;)\s*background:\s*var\(--unifi-selected,\s*transparent\)\s*(?:;|$)/);
});

test('both surfaces have four icon-only, keyboard-accessible appearance choices', async () => {
  const app = await load();
  for (const mount of [app.dashboard(), app.settingsPage()]) {
    const view = mount.render();
    const group = view.find('div', 'Appearance mode');
    assert.equal(group?.role, 'group');
    assert.equal(view.elements[0].props.style, undefined, 'Match Desktop must inherit');
    const glyphs = modes.map(label => {
      const control = button(view, label);
      assert.equal(control.title, label);
      assert.equal(control['aria-pressed'], label === 'Match Desktop');
      assert.equal(control.children.type, 'span');
      assert.equal(control.children.props['aria-hidden'], true);
      return control.children.props.className;
    });
    assert.deepEqual(glyphs, ['mode-device-desktop', 'mode-color-mode', 'mode-sun', 'mode-moon']);
    assert.ok(view.elements.some(node => node.type === 'style' && /\.appearance-option:focus-visible/.test(node.props.children)));
    mount.unmount();
  }
});

test('appearance syncs across surfaces and remount; profile changes reject stale writes', async () => {
  const values = new Map([['sibling.appearance', 'light'], ['unifi.appearance', 'dark']]);
  const app = await load({ profile: 'work / A', values });
  const settings = app.settingsPage(), page = app.dashboard();
  assert.equal(appearance(settings.render()), 'match');
  page.render();
  button(settings.render(), 'Dark').onClick();
  assert.equal(appearance(page.render()), 'dark');
  assert.equal(appearance(app.settingsPage().render()), 'dark');
  const stale = button(settings.render(), 'Light').onClick;
  app.switchProfile('work / B');
  stale();
  assert.equal(app.writes.length, 1);
  assert.equal(appearance(settings.render()), 'match');
  button(page.render(), 'Light').onClick();
  assert.equal(appearance(settings.render()), 'light');
  app.switchProfile('work / A');
  assert.equal(appearance(settings.render()), 'dark');
  assert.deepEqual(app.writes, [
    ['unifi.appearance.v1.local:work%20%2F%20A', 'dark'],
    ['unifi.appearance.v1.local:work%20%2F%20B', 'light'],
  ]);
  assert.equal(values.get('sibling.appearance'), 'light');
  assert.equal(values.get('unifi.appearance'), 'dark');
});

test('System reacts to the device without rewriting appearance and cleans up listeners', async () => {
  const app = await load();
  const page = app.dashboard();
  button(page.render(), 'System').onClick();
  assert.equal(appearance(page.render()), 'light');
  assert.deepEqual(app.listenerCounts(), [1, 1]);
  app.setDark(true);
  assert.equal(appearance(page.render()), 'dark');
  assert.equal(button(page.render(), 'System')['aria-pressed'], true);
  assert.equal(app.writes.length, 1);
  page.unmount();
  assert.deepEqual(app.listenerCounts(), [0, 0]);
});

test('tampered appearance and failed storage readback never change the current theme', async () => {
  for (const options of [{ blockWrites: true }, { readFailure: true }]) {
    const app = await load({ values: new Map([['unifi.appearance.v1.local:default', { choice: 'dark' }]]), ...options });
    const page = app.dashboard();
    assert.equal(appearance(page.render()), 'match');
    button(page.render(), 'Dark').onClick();
    assert.equal(appearance(page.render()), 'match');
    assert.equal(appearance(app.settingsPage().render()), 'match');
  }
});
