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
console = module('test_console', 'dashboard/network_client.py')
diagnostics = module('test_diagnostics_engine', 'dashboard/diagnostics.py')
api = module('test_api', 'dashboard/plugin_api.py')


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('Network access forbidden in tests')
    monkeypatch.setattr(socket.socket, 'connect', denied)
    monkeypatch.setattr(socket.socket, 'connect_ex', denied)
    monkeypatch.setattr(socket, 'getaddrinfo', denied)
    for name in ('UNIFI_API_KEY', 'UNIFI_NETWORK_API_KEY', 'UNIFI_CONSOLE_HOST', 'UNIFI_CONSOLE_CERT_SHA256', 'UNIFI_SHOW_ADDRESSES'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(client, '_retry_until', 0.0)
    monkeypatch.setattr(api.client, '_retry_until', 0.0)
    for mod in {console, getattr(api, 'console', console)}:
        monkeypatch.setattr(mod, '_retry_until', 0.0)
        monkeypatch.setattr(mod, '_handles', {})
        monkeypatch.setattr(mod, '_reverse', {})
        monkeypatch.setattr(mod, '_plugin_settings', lambda: {})


@pytest.fixture
def fixtures():
    return {name: json.loads((ROOT / f'tests/fixtures/{name}.json').read_text()) for name in ('sites', 'devices', 'isp')}


@pytest.fixture
def console_fixture():
    return json.loads((ROOT / 'tests/fixtures/console.json').read_text())


class FakeResponse:
    """Minimal urllib response stand-in: context manager plus bounded read."""

    def __init__(self, body):
        self.body = body

    def read(self, n=-1):
        return self.body if n is None or n < 0 else self.body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None
