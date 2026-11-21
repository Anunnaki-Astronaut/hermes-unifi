"""Agent tools: read-only, bounded inputs, JSON-only output, no secrets, never raise."""
import importlib.util
import json
import sys
from datetime import datetime, timezone

import pytest

from conftest import ROOT, api, console as nc, FakeResponse

NOW = datetime(2026, 11, 14, 12, 0, 30, tzinfo=timezone.utc)


def load(stem):
    spec = importlib.util.spec_from_file_location(f"tools_under_test_{stem}", ROOT / f"{stem}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tools = load("tools")
schemas = load("schemas")
root = load("__init__")


@pytest.fixture(autouse=True)
def wired(monkeypatch, console_fixture):
    """Route the tools at the framework-free service module and serve the synthetic console."""
    service = api._load("service")
    monkeypatch.setattr(tools, "_service", lambda: service)
    monkeypatch.setattr(service, "_cache", {"at": 0.0, "snapshot": None})

    class Opener:
        def open(self, req, timeout=None):
            path = req.full_url.split("/integration/v1", 1)[1].split("?", 1)[0]
            return FakeResponse(json.dumps(console_fixture[path]).encode())
    monkeypatch.setattr(service.console, "opener_for", lambda config, server_name=None: Opener())
    monkeypatch.setattr(service.console, "load_config", lambda *a, **k: service.console.Config("192.168.73.1", None, False, "ephemeral-sentinel"))
    monkeypatch.setattr(service.console, "configured", lambda *a, **k: (True, None))
    monkeypatch.setattr(service.client, "load_key", lambda: (_ for _ in ()).throw(service.client.SafeError("not_configured", 503)))
    return console_fixture


def test_schemas_are_read_only_and_bounded():
    assert set(schemas.ALL) == {"unifi_status", "unifi_diagnose", "unifi_devices", "unifi_clients"} == set(tools.HANDLERS)
    for schema in schemas.ALL.values():
        assert schema["parameters"]["type"] == "object" and schema["parameters"]["required"] == []
        for prop in schema["parameters"]["properties"].values():
            assert prop["type"] == "string"
        text = json.dumps(schema).lower()
        assert "read-only" in text or "never" in text
        for forbidden in ("url", "path", "host", "key", "mac", "restart", "power"):
            assert forbidden not in schema["parameters"]["properties"]
    assert schemas.DIAGNOSE["parameters"]["properties"]["focus"]["enum"] == list(tools.FOCUS_CATEGORIES)


def test_register_wires_every_tool():
    calls = []

    class Ctx:
        def register_tool(self, **kwargs):
            calls.append(kwargs)
    root.register(Ctx())
    assert [c["name"] for c in calls] == list(schemas.ALL)
    assert all(c["toolset"] == "unifi" and c["emoji"] == "📡" and callable(c["handler"]) for c in calls)
    assert all(c["schema"] == schemas.ALL[c["name"]] for c in calls)


def test_status_is_one_plain_english_paragraph():
    result = json.loads(tools.unifi_status({}))
    assert result["ok"] and result["read_only"]
    assert result["summary"].startswith("3 UniFi devices and 3 connected clients checked. 2 critical problems, ")
    assert "Down: Garage AP [address hidden]." in result["summary"]
    assert "not connected" not in result["summary"]
    assert result["sources"] == {"console": True, "consoleCode": None, "cloud": False}


def test_status_without_console_says_so(monkeypatch):
    monkeypatch.setattr(tools._service().console, "configured", lambda *a, **k: (False, "not_configured"))
    result = json.loads(tools.unifi_status({}))
    assert result["ok"] and result["deviceCount"] == 0
    assert result["summary"].startswith("The local UniFi console is not connected")
    assert "devices, clients, Wi-Fi, and ports were not checked" in result["summary"]
    assert "0 UniFi devices" not in result["summary"]


def test_no_misleading_findings_without_a_console(monkeypatch):
    monkeypatch.setattr(tools._service().console, "configured", lambda *a, **k: (False, "not_configured"))
    out = json.loads(tools.unifi_diagnose({}))
    ids = [f["id"] for f in out["findings"]]
    assert "console-not-connected:site" in ids
    assert not [i for i in ids if i.startswith(("wan-missing", "coverage-partial", "all-clear", "device-"))]
    assert out["findings"][0]["recommendation"].startswith("In Settings → Plugins → UniFi")


def test_diagnose_focus_filters_and_describes_fixes():
    everything = json.loads(tools.unifi_diagnose({}))
    assert everything["ok"] and everything["focus"] == "all" and everything["plain_text"].startswith("UniFi network check")
    assert everything["note"].startswith("Fixes are described, not executed")
    wifi = json.loads(tools.unifi_diagnose({"focus": "wifi"}))
    assert wifi["findings"] and all(f["category"] == "wifi" for f in wifi["findings"])
    assert all(f["fix"] is None or f["fix"]["available"] is False for f in everything["findings"])
    stability = json.loads(tools.unifi_diagnose({"focus": "stability"}))
    assert stability["findings"] and all(f["category"] == "stability" for f in stability["findings"])
    assert any(f["id"].startswith("recent-restart") for f in stability["findings"])


def test_diagnose_rejects_unknown_focus():
    result = json.loads(tools.unifi_diagnose({"focus": "everything"}))
    assert result == {"ok": False, "read_only": True, "code": "invalid_input", "status": None,
                      "message": "focus must be one of " + ", ".join(tools.FOCUS_CATEGORIES)}


def test_devices_and_clients_filter_by_query():
    devices = json.loads(tools.unifi_devices({"query": "office"}))
    assert devices["count"] == 1 and devices["items"][0]["name"] == "Office AP"
    assert devices["items"][0]["ports"] == [{"idx": 1, "state": "UP", "speedMbps": 2500, "maxSpeedMbps": 2500, "poe": None}]
    assert devices["items"][0]["radios"][0]["txRetriesPct"] == 31.0
    clients = json.loads(tools.unifi_clients({"query": "phone"}))
    assert clients["count"] == 1 and clients["items"][0]["uplinkName"] == "Garage AP [address hidden]"
    assert json.loads(tools.unifi_clients({}))["count"] == 3
    assert json.loads(tools.unifi_devices({"query": ""}))["count"] == 3


@pytest.mark.parametrize("query", ["x" * 81, 5, ["a"]])
def test_query_bounds(query):
    result = json.loads(tools.unifi_devices({"query": query}))
    assert result["ok"] is False and result["code"] == "invalid_input"


def test_output_never_contains_secrets_or_identifiers():
    blob = "".join(h({}) for h in tools.HANDLERS.values())
    for forbidden in ("ephemeral-sentinel", "10.99.0.", "02:00:00", "aaaaaaaa-0000", "cccccccc-0000", "11111111-1111"):
        assert forbidden not in blob


@pytest.mark.parametrize("code,status", [("authentication_failed", 401), ("certificate_mismatch", 502), ("rate_limited", 429)])
def test_console_errors_become_safe_json(monkeypatch, code, status):
    service = tools._service()

    def fail(*a, **k):
        raise service.console.ConsoleError(code, status)
    monkeypatch.setattr(service.console, "request", fail)
    monkeypatch.setattr(service.console, "snapshot", fail)
    result = json.loads(tools.unifi_devices({}))
    assert result == {"ok": False, "read_only": True, "code": code, "message": nc.MESSAGES[code], "status": status}


def test_unexpected_errors_are_swallowed(monkeypatch):
    monkeypatch.setattr(tools._service(), "cached_snapshot", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret internals")))
    result = json.loads(tools.unifi_devices({}))
    assert result["ok"] is False and result["code"] == "internal_error" and "secret internals" not in json.dumps(result)


def test_handlers_accept_missing_or_non_dict_args():
    for handler in tools.HANDLERS.values():
        assert json.loads(handler())["ok"] is True
        assert json.loads(handler(None))["ok"] is True
        assert json.loads(handler("junk"))["ok"] is True
