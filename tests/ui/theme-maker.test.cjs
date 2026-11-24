'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { load, button } = require('./harness.cjs');

const presets = {
  Daybook: ['F8FAF7 EEF4EF 17302A 27674E D5EBDD', '111A19 1A2725 F3F8F5 A8EBC9 304D3D'],
  Dusk: ['FCF6FA FFFFFF 37253F 794526 EEDDEC', '1B1725 2A2337 F5EAF7 FFBC91 483753'],
  Coast: ['F2FAFB FFFFFF 163B42 166373 D2EAF0', '10252C 193640 E5F7FA 8AD9E6 2C4D58'],
  Marigold: ['FFF9E4 F6E7AE 352600 725000 F9DF82', '211900 342800 FFF0BE FFCD4E 523D00'],
  Cobalt: ['F1F5FF E1E9FF 12234D 234AC5 CFDDFF', '10182F 1B2850 E8F0FF 9FB4FF 304787'],
  Anunnaki: ['FAF8F3 EAE2D3 1C1B1A 704718 E5D3B7', '0C1420 64442D E9EFF6 F1BE77 533829'],
};
const fields = ['Background', 'Panels', 'Text', 'Accent', 'Selected row'];
const root = view => view.elements[0].props;
const setup = async options => {
  const app = await load(options);
  const settings = app.settingsPage();
  const view = () => settings.render();
  const control = label => button(view(), label);
  return { app, settings, view, control, click: label => control(label).onClick(),
    input: label => view().find('input', label)?.value,
    change: (label, value) => view().find(label === 'Edit palette' ? 'select' : 'input', label).onChange({ target: { value } }) };
};

test('collapsed editor previews the exact six presets and three real dots per preset in both modes', async () => {
  const f = await setup();
  const details = f.view().elements.find(node => node.type === 'details');
  assert.ok(details && !details.props.open);
  assert.ok(f.view().find('summary', 'Theme Maker'));
  assert.match(f.view().text, /7 of 8 online.*Studio access point.*24 connected/);
  for (const [index, mode] of ['Light', 'Dark'].entries()) {
    f.change('Edit palette', mode.toLowerCase());
    for (const [name, pair] of Object.entries(presets)) {
      const colors = pair[index].split(' ').map(hex => `#${hex}`);
      const preset = f.control(name);
      const dots = preset.children[0].props.children;
      assert.deepEqual(Array.from(dots, node => node.props.style.background), [colors[1], colors[3], colors[4]]);
      assert.equal(preset.children[1], name, 'dots precede name');
      f.click(name);
      assert.deepEqual(fields.map(field => f.input(`${mode} ${field} hex`)), colors);
      assert.deepEqual(fields.map(field => f.input(`${mode} ${field} swatch`)), colors.map(hex => hex.toLowerCase()));
      assert.equal(f.control(`Apply to ${mode}`).disabled, false);
    }
  }
  assert.deepEqual(f.app.writes, []);
});

test('Anunnaki uses the approved Light and Dark palettes without altering the default or saving until Apply', async () => {
  const f = await setup();
  assert.equal(root(f.view())['data-appearance'], 'match');
  assert.equal(root(f.view()).style, undefined);
  const palettes = [
    ['Light', ['#FAF8F3', '#EAE2D3', '#1C1B1A', '#704718', '#E5D3B7']],
    ['Dark', ['#0C1420', '#64442D', '#E9EFF6', '#F1BE77', '#533829']],
  ];
  for (const [mode, colors] of palettes) {
    f.change('Edit palette', mode.toLowerCase());
    f.click('Anunnaki');
    assert.deepEqual(fields.map(field => f.input(`${mode} ${field} hex`)), colors);
    assert.equal(f.control(`Apply to ${mode}`).disabled, false);
    assert.deepEqual(f.app.writes.map(([key]) => key), mode === 'Light' ? [] : ['unifi.palette.light.v1.local:default']);
    f.click(`Apply to ${mode}`);
  }
  const reload = await setup({ values: f.app.values });
  const dashboard = reload.app.dashboard();
  assert.equal(root(dashboard.render()).style, undefined);
  for (const [mode, [canvas, panel, text, accent, selected]] of palettes) {
    reload.click(mode);
    const style = root(dashboard.render()).style;
    assert.deepEqual([style['--unifi-canvas'], style['--ui-bg-card'], style['--ui-text-primary'], style['--unifi-accent'], style['--unifi-selected']],
      [canvas, panel, text, accent, selected]);
  }
});

test('independent drafts and reset, inactive and active saves, remount and System resolution', async () => {
  const f = await setup();
  f.click('Dark');
  f.click('Dusk');
  f.change('Dark Background hex', '#181320');
  f.change('Edit palette', 'light');
  f.click('Coast');
  f.click('Apply to Light');
  assert.match(f.view().text, /Light palette saved\. Choose Light to see it\./);
  const page = f.app.dashboard();
  assert.equal(root(page.render())['data-appearance'], 'dark');
  assert.equal(root(page.render()).style, undefined);
  f.change('Edit palette', 'dark');
  assert.equal(f.input('Dark Background hex'), '#181320');
  f.click('Reset to preset');
  assert.equal(f.input('Dark Background hex'), '#1B1725');
  f.click('Apply to Dark');
  assert.match(f.view().text, /Dark palette saved\./);
  assert.doesNotMatch(f.view().text, /Choose Dark/);
  assert.equal(root(page.render()).style['--unifi-canvas'], '#1B1725');
  const reload = await setup({ values: f.app.values });
  assert.equal(reload.input('Dark Background hex'), '#1B1725');
  reload.click('Match Desktop');
  assert.equal(root(reload.view()).style, undefined);
  reload.click('System');
  assert.equal(root(reload.view()).style['--unifi-canvas'], '#F2FAFB');
  reload.app.setDark(true);
  assert.equal(root(reload.view()).style['--unifi-canvas'], '#1B1725');
});

test('invalid hex and insufficient contrast are rejected even when a disabled Apply is invoked', async () => {
  const f = await setup();
  for (const [field, value, message] of [
    ['Background', '#ABC', /Background: enter #RRGGBB/],
    ['Text', '#F8FAF7', /Text needs 4\.5:1 against Background/],
    ['Accent', '#F8FAF7', /Accent needs 4\.5:1 against Background/],
    ['Selected row', '#17302A', /Text needs 4\.5:1 against Selected row/],
    ['Selected row', '#678F7E', /Accent needs 3:1 against Selected row/],
  ]) {
    f.click('Daybook');
    f.change(`Light ${field} hex`, value);
    assert.match(f.view().text, message);
    assert.match(f.view().text, /Preview uses the saved palette or Daybook/);
    assert.equal(f.control('Apply to Light').disabled, true);
    f.click('Apply to Light');
    assert.deepEqual(f.app.writes, []);
  }
});

test('profile changes discard drafts; stale Apply cannot save and sibling keys stay untouched', async () => {
  const values = new Map([['sibling.palette', 'untouched']]);
  const f = await setup({ profile: 'A', values });
  f.click('Light');
  f.click('Marigold');
  f.click('Apply to Light');
  f.click('Coast');
  const stale = f.control('Apply to Light').onClick;
  f.app.switchProfile('B');
  stale();
  assert.equal(f.app.writes.length, 2);
  assert.equal(f.input('Light Background hex'), '#F8FAF7');
  assert.equal(root(f.view()).style, undefined);
  f.app.switchProfile('A');
  assert.equal(f.input('Light Background hex'), '#FFF9E4');
  assert.equal(root(f.view()).style['--unifi-canvas'], '#FFF9E4');
  assert.equal(values.get('sibling.palette'), 'untouched');
  assert.deepEqual(f.app.writes.map(([key]) => key), ['unifi.appearance.v1.local:A', 'unifi.palette.light.v1.local:A']);
});

for (const [profile, encodedProfile] of [['default', 'default'], ['office & bench/2', 'office%20%26%20bench%2F2']]) {
  test(`connections sharing profile "${profile}" isolate preferences and discard drafts`, async () => {
    const f = await setup({ connectionId: 'source:A', profile });
    const page = f.app.dashboard();
    f.click('Light');
    f.click('Marigold');
    f.click('Apply to Light');
    assert.equal(root(page.render()).style['--unifi-canvas'], '#FFF9E4');
    f.click('Coast');
    const staleApply = f.control('Apply to Light').onClick;
    const staleAppearance = button(page.render(), 'Dark').onClick;

    f.app.switchConnection('source:B');
    staleApply();
    staleAppearance();
    assert.equal(f.app.writes.length, 2, 'handlers from the previous connection must not write before rerender');
    assert.equal(root(page.render())['data-appearance'], 'match');
    assert.equal(root(page.render()).style, undefined);
    assert.equal(f.input('Light Background hex'), '#F8FAF7');
    assert.equal(f.app.connectionListenerCount(), 2);
    f.click('Light');
    f.click('Cobalt');
    f.click('Apply to Light');
    assert.equal(root(page.render()).style['--unifi-canvas'], '#F1F5FF');
    f.click('Open Agent settings');
    assert.equal(new URL(f.app.navigations.at(-1), 'https://example.invalid').searchParams.get('profile'), profile);

    f.app.switchConnection('source:A');
    assert.equal(f.input('Light Background hex'), '#FFF9E4', 'restore saved palette, not the unsaved Coast draft');
    assert.equal(root(page.render()).style['--unifi-canvas'], '#FFF9E4');
    f.app.switchConnection('source:B');
    assert.equal(f.input('Light Background hex'), '#F1F5FF');
    assert.deepEqual(f.app.writes.map(([key]) => key), [
      `unifi.appearance.v1.source%3AA:${encodedProfile}`, `unifi.palette.light.v1.source%3AA:${encodedProfile}`,
      `unifi.appearance.v1.source%3AB:${encodedProfile}`, `unifi.palette.light.v1.source%3AB:${encodedProfile}`,
    ]);
    page.unmount();
    f.settings.unmount();
    assert.equal(f.app.connectionListenerCount(), 0);
  });
}

test('older SDK without connection state still scopes preferences and drafts by profile', async () => {
  const f = await setup({ noConnectionState: true, profile: 'office' });
  f.click('Light');
  f.click('Coast');
  f.click('Apply to Light');
  f.click('Cobalt');
  const staleApply = f.control('Apply to Light').onClick;
  f.app.switchProfile('default');
  staleApply();
  assert.equal(root(f.view())['data-appearance'], 'match');
  assert.equal(f.input('Light Background hex'), '#F8FAF7');
  f.app.switchProfile('office');
  assert.equal(root(f.view()).style['--unifi-canvas'], '#F2FAFB');
  assert.equal(f.input('Light Background hex'), '#F2FAFB');
  assert.deepEqual(f.app.writes.map(([key]) => key), ['unifi.appearance.v1.:office', 'unifi.palette.light.v1.:office']);
});

test('tampered palettes are ignored and failed storage readback is not published', async () => {
  for (const options of [{ blockWrites: true }, { readFailure: true }]) {
    const f = await setup({ ...options, values: new Map([
      ['unifi.appearance.v1.local:default', 'light'],
      ['unifi.palette.light.v1.local:default', { background: 'url(invalid)' }],
    ]) });
    assert.equal(root(f.view()).style, undefined);
    f.click('Coast');
    f.click('Apply to Light');
    assert.match(f.view().text, /Palette was not saved/);
    assert.equal(root(f.view()).style, undefined);
  }
});
