import inspect
import re
from fastapi import HTTPException
from starlette.routing import Match
from types import SimpleNamespace
import json
import pytest
from conftest import api, ROOT


@pytest.fixture
def http():
    # Exercise the registered endpoint and Starlette method matching without a
    # threaded TestClient portal (unavailable in the restricted worker).
    class LocalClient:
        def request(self, method, path):
            for route in api.router.routes:
                match, _ = route.matches({'type':'http','path':path,'method':method,'root_path':''})
                if match == Match.PARTIAL:
                    return SimpleNamespace(status_code=405)
                if match == Match.FULL:
                    try:
                        body, status, headers = route.endpoint(), 200, {}
                    except HTTPException as exc:
                        body, status, headers = {'detail':exc.detail}, exc.status_code, exc.headers or {}
                    return SimpleNamespace(status_code=status, json=lambda:body, text=json.dumps(body), headers=headers)
            return SimpleNamespace(status_code=404)
        def __getattr__(self, method):
            return lambda path: self.request(method.upper(),path)
    return LocalClient()


@pytest.mark.parametrize('configured', [False,True])
def test_health(http,monkeypatch,configured):
    def key():
        if not configured:
            raise api.client.SafeError('not_configured',503)
        return 'ephemeral-sentinel'
    monkeypatch.setattr(api.client,'load_key',key)
    monkeypatch.setattr(api.client,'request_data',lambda _: pytest.fail('health contacted transport'))
    response = http.get('/health')
    assert response.status_code == 200
    assert response.json() == {'ok':True,'configured':configured,'connected':None,'read_only':True,'version':'0.1.0'}


def test_routes(http):
    assert {r.path for r in api.router.routes} == {'/health','/overview','/sites','/devices','/isp'}
    for route in api.router.routes:
        assert route.methods == {'GET'}
        assert not inspect.signature(route.endpoint).parameters
        for method in ('post','put','patch','delete'):
            assert getattr(http,method)(route.path).status_code == 405


@pytest.mark.parametrize('view',['sites','devices','isp','overview'])
def test_views(http,monkeypatch,fixtures,view):
    monkeypatch.setattr(api.client,'request_data',lambda v: (fixtures[v]['data'],False,'ephemeral-sentinel'))
    response = http.get('/'+view)
    assert response.status_code == 200 and response.json()['ok']
    assert 'synthetic-host' not in response.text
    assert 'ephemeral-sentinel' not in response.text


@pytest.mark.parametrize('code,status',[('not_configured',503),('authentication_failed',401),('rate_limited',429),('unifi_unreachable',502),('invalid_upstream_response',502)])
def test_errors(http,monkeypatch,code,status):
    def fail(_):
        raise api.client.SafeError(code,status,12 if code=='rate_limited' else None)
    monkeypatch.setattr(api.client,'view_data',fail)
    response = http.get('/sites')
    assert response.status_code == status
    assert response.json() == {'detail':{'code':code,'message':api.client.MESSAGES[code]}}
    if code=='rate_limited':
        assert response.headers['Retry-After']=='12'


def test_partial_overview(http,monkeypatch,fixtures):
    def get(v):
        if v=='devices':
            raise api.client.SafeError('unifi_unreachable')
        return fixtures[v]['data'],False,'ephemeral-sentinel'
    monkeypatch.setattr(api.client,'request_data',get)
    data = http.get('/overview').json()['data']
    assert data['partial'] and data['degraded']
    assert set(data['summaries']) == {'sites','isp'}


def test_renderer_contract():
    source = (ROOT/'desktop/plugin.js').read_text()
    assert set(re.findall(r"from '([^']+)'",source)) == {'react','react/jsx-runtime','@hermes/plugin-sdk'}
    assert set(re.findall(r"ctx.rest\('([^']+)'\)",source)) == {'/health','/overview','/sites','/devices','/isp'}
    assert 'useQuery({' in source and 'refetchInterval: 60000' in source
    assert not re.search(r'\bfetch\(|setInterval|XMLHttpRequest|https://',source)
    assert 'defaultEnabled: false' in source
    assert source.count("path: '/unifi'") == 2
    assert "host.navigate('/unifi')" in source
    assert "children: 'Read only'" in source


def render_preview(tmp_path, view, payload=None):
    import subprocess
    script = (ROOT/'scripts/render_screenshot.cjs').read_text()
    if payload is not None:
        script = script.replace('const element =', f'payloads[{json.dumps(view)}] = {json.dumps(payload)};\nconst element =', 1)
    script = script.replace('const element =', '''
function freeze(value) {
  if (value && typeof value === 'object') {
    Object.values(value).forEach(freeze);
    Object.freeze(value);
  }
}
freeze(payloads);
const sourceSnapshot = JSON.parse(JSON.stringify(payloads));
const element =''', 1)
    # Compare the actual JS objects consumed by the renderer, not the Python input.
    script = script.replace('  const output =', '''
  require('node:assert/strict').deepStrictEqual(payloads, sourceSnapshot,
    'Display formatting must not mutate source payloads');
  const output =''', 1)
    output = tmp_path/f'{view}.html'
    subprocess.run(['node', '--experimental-vm-modules', '-', view, str(output)],
                   input=script, text=True, cwd=ROOT/'scripts', check=True, capture_output=True)
    return output.read_text()


@pytest.mark.parametrize('view', ['overview', 'sites', 'devices', 'isp'])
def test_deterministic_previews(tmp_path, view):
    html = render_preview(tmp_path, view)
    assert html == (ROOT/f'docs/screenshots/{view}.html').read_text()
    assert html.count(' aria-pressed="true"') == 1
    assert html.count(' aria-pressed="false"') == 3
    assert '[aria-pressed="true"]' in html  # CSS must remain raw text.
    assert 'Data notes' in html and 'Read only' in html
    if view != 'overview':
        assert '<th scope="col"' in html
        assert 'tabindex="0" role="region"' in html
        assert '1 item' in html
        title = {'sites': 'Sites', 'devices': 'Devices', 'isp': 'ISP Health'}[view]
        assert html.count(f'<h2>{title}</h2>') == 1
        assert f'<section class="table-shell" aria-label="UniFi {title}">' in html
        assert f'<table aria-label="UniFi {title}">' in html


def test_display_formatting_does_not_mutate_source_payloads(tmp_path):
    # render_preview freezes all nested JS data and asserts deep equality after render.
    # These raw enum/empty values must format differently without changing that data.
    payload = {'items': [
        {'name': 'Example', 'status': 'offline', 'firmwareStatus': 'updateAvailable', 'version': '', 'model': 'Unknown'},
        {'name': 'Second', 'status': 'online', 'firmwareStatus': 'upToDate', 'updateAvailable': None},
    ], 'partial': True, 'degraded': True, 'notice': 'Only the first upstream page is shown.'}
    html = render_preview(tmp_path, 'devices', payload)
    assert 'Partial data.' in html and payload['notice'] in html
    assert 'Degraded —' in html and 'Needs attention' in html
    assert '>Offline</span>' in html and '>Online</span>' in html
    assert '>Update available</span>' in html and '>Up to date</span>' in html
    assert '<span class="muted">Unknown</span>' in html
    assert '<span class="muted">—</span>' in html
    assert 'class="row-attention bad"' in html


def test_summary_and_empty_states(tmp_path):
    html = render_preview(tmp_path, 'overview', {'summaries': {
        'sites': {'count': 0, 'partial': True, 'degraded': False},
        'devices': {'count': 2, 'partial': False, 'degraded': True},
        'isp': {'count': 1, 'partial': False, 'degraded': False},
    }})
    assert 'Partial count · Incomplete reporting' in html
    assert 'Needs attention' in html and 'No reported issues' in html
    html = render_preview(tmp_path, 'sites', {'items': []})
    assert '0 items' in html and 'No data available.' in html


def test_numeric_columns_and_isp_attention(tmp_path):
    html = render_preview(tmp_path, 'isp', {'items': [{'label': '123', 'packetLoss': 1, 'downtime': 0}]})
    assert '<td><span>123</span><span class="row-note">Needs attention</span></td>' in html
    assert '<td class="numeric"><span>1</span></td>' in html
    assert '<td class="numeric"><span>0</span></td>' in html
    assert '<td class="numeric"><span class="muted">—</span></td>' in html
    assert 'latency (ms)' not in html and 'Uptime (%)' not in html


def test_raw_unknown_device_status_is_muted_without_row_attention(tmp_path):
    html = render_preview(tmp_path, 'devices', {'items': [
        {'name': 'Unreported device', 'status': 'unknown'},
    ], 'degraded': False})
    assert '<span class="muted">Unknown</span>' in html
    assert not re.search(r'<tr class="row-attention\b', html)
    assert 'Needs attention' not in html
    assert 'Degraded —' not in html


def test_firmware_only_availability_keeps_pill_without_row_attention(tmp_path):
    html = render_preview(tmp_path, 'devices', {'items': [
        {'name': 'Online device', 'status': 'online', 'firmwareStatus': 'updateAvailable'},
    ], 'degraded': False})
    assert '<span class="pill warn">Update available</span>' in html
    assert not re.search(r'<tr class="row-attention\b', html)
    assert 'Needs attention' not in html
    assert 'Degraded —' not in html


DISCLAIMER = ('Unofficial integration. UniFi is a trademark of Ubiquiti Inc. '
              'This project is not affiliated with or endorsed by Ubiquiti.')


def test_brand_and_semantic_css(tmp_path):
    source = (ROOT/'desktop/plugin.js').read_text()
    css = source.split('const CSS = `', 1)[1].split('`;', 1)[0]
    assert not re.search(r'\.mark\b|className: [\'\"]mark[\'\"]', source)
    assert not re.search(r'https?://|<img|<svg|jsx[s]?\([\'\"](?:img|svg)', source)
    assert re.search(r'\.unifi h1\{[^}]*font-size:24px;[^}]*font-weight:700', css)
    for tone, token in [('good', 'success'), ('warn', 'yellow'), ('bad', 'red'), ('muted', 'text-secondary')]:
        assert f'--unifi-{tone}:var(--ui-{token})' in css
        assert f'color:var(--unifi-{tone})' in css
    assert not re.search(r'#[\da-fA-F]{3,8}\b|\b(?:rgb|rgba|hsl|hsla|oklch|color)\(', css)
    # Color declarations must use theme tokens or CSS inheritance/transparent.
    for value in re.findall(r'(?:color|background(?:-color)?|border(?:-(?:top|left))?(?:-color)?|outline):([^;}]+)', css):
        assert 'var(--' in value or any(v in value for v in ('transparent', 'currentColor')) or value == '0'
    assert 'jsx(StatusDot,' in source
    assert source.count(DISCLAIMER) == 1
    assert (ROOT/'README.md').read_text().count(DISCLAIMER) == 1
    for view in ('overview', 'sites', 'devices', 'isp'):
        html = render_preview(tmp_path, view)
        assert re.findall(r'<h1[^>]*>(.*?)</h1>', html) == ['UniFi']
        assert html.count(DISCLAIMER) == 1
        assert DISCLAIMER in html.split('<footer>', 1)[1]
        assert (ROOT/f'docs/screenshots/{view}.html').read_text().count(DISCLAIMER) == 1
        assert '<span class="readonly muted">Read only</span>' in html


@pytest.mark.parametrize('state,tone', [
    ('healthy', 'good'), ('online', 'good'), ('connected', 'good'), ('upToDate', 'good'),
    ('warning', 'warn'), ('updateAvailable', 'warn'), ('updating', 'warn'),
    ('pending', 'warn'), ('degraded', 'warn'), ('partial', 'warn'),
    ('offline', 'bad'), ('disconnected', 'bad'), ('error', 'bad'), ('errors', 'bad'),
    ('unknown', 'muted'), ('—', 'muted'), ('', 'muted'), ('read-only', 'muted'), ('neutral', 'muted'),
])
def test_semantic_status_and_row_tones(tmp_path, state, tone):
    html = render_preview(tmp_path, 'devices', {'items': [{'name': 'Device', 'status': state, 'firmwareStatus': state}]})
    row = html.split('<tbody>', 1)[1].split('</tbody>', 1)[0]
    assert row.count(f'class="pill {tone}"' if tone != 'muted' else 'class="muted"') >= 2
    if tone in ('warn', 'bad'):
        assert f'<tr class="row-attention {tone}">' in row
    else:
        assert 'row-attention' not in row


def test_overview_semantic_tones(tmp_path):
    for state, tone in [('healthy', 'good'), ('degraded', 'warn'), ('partial', 'warn'), ('offline', 'bad'), ('error', 'bad')]:
        html = render_preview(tmp_path, 'overview', {'degraded': True, 'partial': True, 'summaries': {
            'sites': {'count': 1, 'status': state, 'degraded': state != 'healthy', 'partial': state == 'partial'},
        }})
        assert re.search(rf'<article class="[^"]*\b{tone}\b', html)
        assert html.count('class="notice warn"') == 2


def test_unofficial_descriptions():
    for path in ('plugin.yaml', 'dashboard/manifest.json', 'README.md'):
        text = (ROOT/path).read_text()
        assert 'unofficial integration' in text.lower()
        assert 'official UniFi Site Manager API' in text
        assert 'Read-only official' not in text
