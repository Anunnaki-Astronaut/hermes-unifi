import io
import json
import ssl
import types
from urllib.error import HTTPError, URLError
import pytest
from conftest import client as c


@pytest.fixture
def secret(monkeypatch):
    # Ephemeral sentinel, never a credential or fixture value.
    import secrets
    value = secrets.token_urlsafe(24)
    monkeypatch.setattr(c, 'load_key', lambda: value)
    return value


def transport(monkeypatch, payload=None, error=None, inspect=None):
    def build(*handlers):
        assert handlers[0].proxies == {}
        context = handlers[1]._context
        assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
        assert isinstance(handlers[2], c.NoRedirect)
        def open(req, timeout):
            if inspect:
                inspect(req, timeout)
            if error:
                raise error
            return io.BytesIO(payload)
        return types.SimpleNamespace(open=open)
    monkeypatch.setattr(c, 'build_opener', build)


def test_missing_and_settings_ignored(monkeypatch):
    def absent(name):
        raise ModuleNotFoundError(name='agent.secret_scope')
    monkeypatch.setattr(c.importlib, 'import_module', absent)
    with pytest.raises(c.SafeError, match='Configure'):
        c.load_key({'api_key': 'ignored'})
    monkeypatch.setenv('UNIFI_API_KEY', 'standalone-sentinel')
    assert c.load_key() == 'standalone-sentinel'


@pytest.mark.parametrize('failure', [RuntimeError, ImportError, type('UnscopedSecretError', (Exception,), {})])
def test_scope_failure_closed(monkeypatch, failure):
    def get_secret(*args):
        raise failure('private diagnostic')
    monkeypatch.setattr(c.importlib, 'import_module', lambda _: types.SimpleNamespace(get_secret=get_secret))
    monkeypatch.setenv('UNIFI_API_KEY', 'must-not-fallback')
    with pytest.raises(c.SafeError) as e:
        c.load_key()
    assert 'private' not in str(e.value)


def test_broken_module_closed(monkeypatch):
    def broken(name):
        raise ModuleNotFoundError(name='dependency')
    monkeypatch.setattr(c.importlib, 'import_module', broken)
    with pytest.raises(c.SafeError):
        c.load_key()


@pytest.mark.parametrize('view,path', [('sites','/sites'),('devices','/devices'),('isp','/isp-metrics/5m')])
def test_transport(monkeypatch, fixtures, secret, view, path):
    def inspect(req, timeout):
        assert req.full_url == 'https://api.ui.com/v1' + path
        assert req.method == 'GET' and req.data is None and timeout == 10
        assert req.get_header('X-api-key') == secret
        assert req.get_header('User-agent') == 'Hermes-UniFi/0.1.0'
        assert secret not in req.full_url
    transport(monkeypatch, json.dumps(fixtures[view]).encode(), inspect=inspect)
    rows, partial, _ = c.request_data(view)
    assert rows and not partial


@pytest.mark.parametrize('view', ['hosts','https://example.com','../sites','isp-metrics/1h','POST'])
def test_allowlist(view):
    with pytest.raises(ValueError):
        c.request_data(view)


@pytest.mark.parametrize('timeout', [0,31,float('nan'),float('inf'),True,'10'])
def test_timeout_bounds(timeout):
    with pytest.raises(ValueError):
        c.request_data('sites', timeout)


def test_redirect_denied():
    assert c.NoRedirect().redirect_request(None,None,302,'',{},'https://elsewhere.invalid') is None


@pytest.mark.parametrize('status,code', [(401,'authentication_failed'),(403,'authentication_failed'),(429,'rate_limited'),(500,'upstream_http_error'),(302,'upstream_http_error')])
def test_http_errors(monkeypatch, secret, status, code):
    transport(monkeypatch, error=HTTPError('private-url',status,'private-message',{'Retry-After':'12'},io.BytesIO(b'private-body')))
    with pytest.raises(c.SafeError) as e:
        c.request_data('sites')
    assert e.value.code == code
    assert e.value.retry_after == (12 if status == 429 else None)
    assert 'private' not in str(e.value) and secret not in str(e.value)


@pytest.mark.parametrize('value,expected', [
    ('0', 0), ('5', 5), ('86400', 86400), ('999999', 86400),
    ('0.0', 0), ('5.0', 5), ('1.5', 2), ('5.3', 6),
    ('0.000001', 1), ('5.000001', 6), ('5.999999', 6),
    ('86399.000001', 86400), ('86400.1', 86400), ('999999.999999', 86400),
    (' \t5.3\t ', 6), ('000005.300000', 6),
])
def test_retry_after(value,expected):
    assert c.retry_seconds(value) == expected


@pytest.mark.parametrize('value', [
    None, 5, 5.3, True, float('nan'), float('inf'),
    '', ' ', '-1', '-0.1', '+5', 'NaN', 'nan', 'Infinity', 'inf', '-inf',
    'Wed, 21 Oct 2015 07:28:00 GMT', 'secret', '5s', '1e2', '5.3junk',
    '.5', '5.', '5..3', '5 .3', '５.３', '5.3\n',
    '1000000', '0000005', '0.0000001', '5.3000000', '9' * 1000,
    ' ' * 32 + '5',
])
def test_retry_after_rejects_invalid(value):
    assert c.retry_seconds(value) is None


@pytest.mark.parametrize('error', [URLError('private'),TimeoutError('private'),OSError('private')])
def test_network_errors(monkeypatch, secret, error):
    transport(monkeypatch,error=error)
    with pytest.raises(c.SafeError) as e:
        c.request_data('sites')
    assert e.value.code == 'unifi_unreachable' and 'private' not in str(e.value)


@pytest.mark.parametrize('payload', [b'bad',b'[]',b'{}',b'{"data": []}', b'{"httpStatusCode":200,"traceId":"x","data":[null]}', b'x'*(c.MAX_BYTES+1)], ids=['bad-json','array','empty','missing-envelope','null-row','oversized'])
def test_invalid(monkeypatch, secret, payload):
    transport(monkeypatch,payload)
    with pytest.raises(c.SafeError) as e:
        c.request_data('sites')
    assert e.value.code == 'invalid_upstream_response'


def test_projection(fixtures, secret):
    output = {v:c.project(v,p['data'],secret) for v,p in fixtures.items()}
    encoded = json.dumps(output)
    for forbidden in ('synthetic-site','synthetic-host','synthetic-device','02:00','192.0.2.1','wifiClient','periods','999','traceId','ispAsn'):
        assert forbidden not in encoded
    assert output['isp'][0]['avgLatency'] == 10
    assert output['sites'][0]['offlineDevices'] == 1
    assert set(output['devices'][0]) == {'name','model','productLine','status','version','firmwareStatus','updateAvailable'}


def test_names_redacted(fixtures, secret):
    row = fixtures['devices']['data'][0]['devices'][0]
    for value in (secret, '192.0.2.1', '02:00:00:00:00:01', '2001:db8::1', 'synthetic-device'):
        row['name'] = value
        assert c.project('devices',fixtures['devices']['data'],secret)[0]['name'] is None


def test_latest_across_duplicate_groups(fixtures, secret):
    rows = fixtures['isp']['data']
    rows.append({**rows[0], 'periods': [rows[0]['periods'][1]]})
    assert len(c.project('isp',rows,secret)) == 1


def test_partial_and_empty(monkeypatch, secret):
    monkeypatch.setattr(c, 'request_data', lambda _: ([],True,secret))
    assert c.view_data('sites') == {'items':[], 'partial':True, 'degraded':False,'notice':'Only the first upstream page is shown.'}


def test_neutral_device_statuses():
    assert c.NEUTRAL_DEVICE_STATUSES == {None, 'online', 'unknown'}
    assert 'Unknown' not in c.NEUTRAL_DEVICE_STATUSES


@pytest.mark.parametrize('status,degraded', [
    (None, False), ('online', False), ('unknown', False),
    ('offline', True), ('disconnected', True), ('updating', True),
    ('', True), ('Unknown', True), ('UNKNOWN', True),
])
def test_device_status_degraded(monkeypatch, secret, status, degraded):
    rows = [{'devices': [{'status': status}]}]
    monkeypatch.setattr(c, 'request_data', lambda _: (rows, False, secret))
    data = c.view_data('devices')
    assert data['items'][0]['status'] == status
    assert data['degraded'] is degraded
    assert data['partial'] is False
    assert data['notice'] is None


@pytest.mark.parametrize('signal', [
    'offlineDevice', 'pendingUpdateDevice', 'wanUptime', 'packetLoss', 'downtime',
])
@pytest.mark.parametrize('degraded', [False, True])
def test_non_status_degraded_signals(monkeypatch, secret, signal, degraded):
    value = (99 if degraded else 100) if signal == 'wanUptime' else int(degraded)
    if signal in ('offlineDevice', 'pendingUpdateDevice', 'wanUptime'):
        view = 'sites'
        group = 'percentages' if signal == 'wanUptime' else 'counts'
        rows = [{'statistics': {group: {signal: value}}}]
    else:
        view = 'isp'
        rows = [{'hostId': 'synthetic-host', 'siteId': 'synthetic-site',
                 'metricType': '5m', 'periods': [
                     {'metricTime': '2026-01-01T00:00:00Z',
                      'data': {'wan': {signal: value}}}]}]
    monkeypatch.setattr(c, 'request_data', lambda _: (rows, False, secret))
    assert c.view_data(view)['degraded'] is degraded


@pytest.mark.parametrize('status,degraded', [('unknown', False), ('offline', True)])
def test_overview_device_status(monkeypatch, secret, status, degraded):
    rows = {
        'sites': [{'statistics': {'counts': {'offlineDevice': 0, 'pendingUpdateDevice': 0},
                                  'percentages': {'wanUptime': 100}}}],
        'devices': [{'devices': [{'status': status}]}],
        'isp': [{'hostId': 'synthetic-host', 'siteId': 'synthetic-site',
                 'metricType': '5m', 'periods': [
                     {'metricTime': '2026-01-01T00:00:00Z',
                      'data': {'wan': {'packetLoss': 0, 'downtime': 0, 'uptime': 100}}}]}],
    }
    monkeypatch.setattr(c, 'request_data', lambda view: (rows[view], False, secret))
    assert c.overview_data() == {
        'summaries': {
            'sites': {'count': 1, 'degraded': False, 'partial': False},
            'devices': {'count': 1, 'degraded': degraded, 'partial': False},
            'isp': {'count': 1, 'degraded': False, 'partial': False},
        },
        'errors': [], 'partial': False, 'degraded': degraded,
    }


@pytest.mark.parametrize('value,expected', [('120', 120), ('5.3', 6)])
def test_backoff_prevents_outbound_call(monkeypatch, secret, value, expected):
    monkeypatch.setattr(c.time, 'monotonic', lambda: 100)
    transport(monkeypatch,error=HTTPError('private',429,'',{'Retry-After':value},io.BytesIO()))
    with pytest.raises(c.SafeError) as first:
        c.request_data('sites')
    assert first.value.retry_after == expected
    monkeypatch.setattr(c,'build_opener',lambda *_: pytest.fail('backoff ignored'))
    with pytest.raises(c.SafeError) as e:
        c.request_data('devices')
    assert e.value.retry_after == expected


def test_read_is_bounded(monkeypatch, secret):
    class Response(io.BytesIO):
        def read(self, size):
            assert size == c.MAX_BYTES + 1
            return super().read(size)
    monkeypatch.setattr(c,'build_opener', lambda *_: types.SimpleNamespace(open=lambda *a,**k:Response(b'{}')))
    with pytest.raises(c.SafeError):
        c.request_data('sites')


def test_preview_matches_projection(fixtures):
    from conftest import ROOT
    expected = json.loads((ROOT/'tests/fixtures/preview.json').read_text())
    for view,payload in fixtures.items():
        assert expected[view]['items'] == c.project(view,payload['data'],'ephemeral-sentinel')
