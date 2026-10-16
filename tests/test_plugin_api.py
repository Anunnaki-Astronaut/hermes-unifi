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
