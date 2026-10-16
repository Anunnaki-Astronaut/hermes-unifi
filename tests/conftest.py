import importlib.util
import json
import socket
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


client = module('test_client', 'dashboard/unifi_client.py')
api = module('test_api', 'dashboard/plugin_api.py')


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('Network access forbidden in tests')
    monkeypatch.setattr(socket.socket, 'connect', denied)
    monkeypatch.setattr(socket.socket, 'connect_ex', denied)
    monkeypatch.setattr(socket, 'getaddrinfo', denied)
    monkeypatch.delenv('UNIFI_API_KEY', raising=False)
    monkeypatch.setattr(client, '_retry_until', 0.0)
    monkeypatch.setattr(api.client, '_retry_until', 0.0)


@pytest.fixture
def fixtures():
    return {name: json.loads((ROOT / f'tests/fixtures/{name}.json').read_text()) for name in ('sites', 'devices', 'isp')}
