"""Local console client: configuration boundaries, transport mapping, privacy projections. No network."""
import io
import json
import ssl
from datetime import datetime, timezone
from email.message import Message
from urllib.error import HTTPError, URLError

import pytest

from conftest import console as nc, console_fixture, FakeResponse

NOW = datetime(2026, 11, 14, 12, 0, 30, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def pinned_resolver(monkeypatch):
    """Hostnames resolve to a private address without touching DNS or sockets."""
    monkeypatch.setattr(nc.socket, "getaddrinfo",
                        lambda host, port, **k: [(2, 1, 6, "", (f"192.168.73.{len(host) % 200 + 2}", port))])


@pytest.fixture
def config():
    return nc.Config("192.168.73.1", None, False, "ephemeral-sentinel")


@pytest.fixture
def fake_console(monkeypatch, console_fixture):
    """Serve fixture payloads keyed by path; record every request."""
    calls = []

    class Opener:
        def open(self, req, timeout=None):
            calls.append(req)
            assert req.get_method() == "GET"
            assert req.full_url.startswith("https://192.168.73.1/proxy/network/integration/v1/")
            path = req.full_url.split("/integration/v1", 1)[1].split("?", 1)[0]
            if path not in console_fixture:
                raise HTTPError(req.full_url, 404, "Not Found", Message(), io.BytesIO(b"{}"))
            body = json.dumps(console_fixture[path]).encode()
            return FakeResponse(body)
    monkeypatch.setattr(nc, "opener_for", lambda config, server_name=None: Opener())
    return calls


# ----------------------------------------------------------------------------- configuration

@pytest.mark.parametrize("raw,expected", [
    ("192.168.73.1", "192.168.73.1"), (" 10.0.0.5:8443 ", "10.0.0.5:8443"), ("172.16.4.4", "172.16.4.4"),
    ("169.254.1.1", "169.254.1.1"), ("unifi", "unifi"), ("console.local", "console.local"), ("Gateway.LAN", "gateway.lan"),
    ("fd00::1", "[fd00::1]"), ("[fd00::1]:443", "[fd00::1]:443"),
])
def test_valid_console_hosts(raw, expected):
    assert nc.validate_host(raw) == expected


@pytest.mark.parametrize("raw", [
    "8.8.8.8", "1.1.1.1:443", "127.0.0.1", "0.0.0.0", "224.0.0.1", "2607:f8b0::1", "::1", "unifi.ui.com", "api.ui.com",
    "https://192.168.73.1", "192.168.73.1/proxy", "192.168.73.1?x=1", "user@192.168.73.1", "192.168.73.1:0",
    "192.168.73.1:70000", "bad host", "-x.local", "a" * 300,
])
def test_invalid_console_hosts(raw):
    with pytest.raises(nc.ConsoleError) as info:
        nc.validate_host(raw)
    assert info.value.code == "invalid_console_host"


def test_empty_host_is_not_configured():
    with pytest.raises(nc.ConsoleError) as info:
        nc.validate_host("")
    assert info.value.code == "not_configured" and info.value.status == 503


@pytest.mark.parametrize("raw,expected", [
    ("", None), (None, None), ("AB" * 32, "ab" * 32),
    (":".join(["ab"] * 32), "ab" * 32), (" " + "0" * 64 + "\n", "0" * 64),
])
def test_pin_normalisation(raw, expected):
    assert nc.validate_pin(raw) == expected


@pytest.mark.parametrize("raw", ["abc", "g" * 64, "0" * 63, "0" * 65, 12345])
def test_pin_rejects_invalid(raw):
    with pytest.raises(nc.ConsoleError) as info:
        nc.validate_pin(raw)
    assert info.value.code == "invalid_certificate_pin"


def test_load_config_reads_settings_and_secret(monkeypatch):
    monkeypatch.setattr(nc, "load_secret", lambda name, environ=None: "ephemeral-sentinel")
    config = nc.load_config({"console_host": "192.168.73.1", "console_cert_sha256": "A" * 64, "show_addresses": "true"}, {})
    assert (config.host, config.pin, config.show_addresses, config.key) == ("192.168.73.1", "a" * 64, True, "ephemeral-sentinel")
    assert nc.configured({"console_host": "192.168.73.1"}, {}) == (True, None)


def test_load_config_without_secret_is_not_configured(monkeypatch):
    monkeypatch.setattr(nc, "load_secret", lambda name, environ=None: (_ for _ in ()).throw(nc.ConsoleError("not_configured", 503)))
    assert nc.configured({"console_host": "192.168.73.1"}, {}) == (False, "not_configured")
    assert nc.configured({}, {}) == (False, "not_configured")
    assert nc.configured({"console_host": "example.com"}, {}) == (False, "invalid_console_host")


def test_secret_rejects_control_characters(monkeypatch):
    with pytest.raises(nc.ConsoleError):
        nc.load_secret("UNIFI_NETWORK_API_KEY", {"UNIFI_NETWORK_API_KEY": "bad\nkey"})
    with pytest.raises(nc.ConsoleError):
        nc.load_secret("UNIFI_NETWORK_API_KEY", {})


# ----------------------------------------------------------------------------- transport

def test_request_builds_fixed_url_and_headers(fake_console, config):
    payload = nc.request("/info", config=config)
    assert payload == {"applicationVersion": "9.9.99"}
    req = fake_console[0]
    assert req.full_url == "https://192.168.73.1/proxy/network/integration/v1/info"
    assert req.get_header("X-api-key") == "ephemeral-sentinel"
    assert req.get_header("User-agent") == "Hermes-UniFi/0.3.0"
    assert req.get_header("Accept") == "application/json"


@pytest.mark.parametrize("path", ["info", "/../admin", "/info?x=1", "/info#f", "//info", 5])
def test_request_rejects_unsafe_paths(path, config):
    with pytest.raises(ValueError):
        nc.request(path, config=config)


@pytest.mark.parametrize("timeout", [0, 31, True, "10"])
def test_request_timeout_bounds(timeout, config):
    with pytest.raises(ValueError):
        nc.request("/info", timeout=timeout, config=config)


def test_redirects_are_refused():
    assert nc.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil") is None


def test_pinned_handler_replaces_ca_check_with_fingerprint():
    handler = nc.PinnedHTTPSHandler("a" * 64)
    assert handler.pinned_context.verify_mode == ssl.CERT_NONE and handler.pinned_context.check_hostname is False
    plain = nc.opener_for(nc.Config("192.168.73.1", None, False, "k"))
    assert not any(isinstance(h, nc.PinnedHTTPSHandler) for h in plain.handlers)
    pinned = nc.opener_for(nc.Config("192.168.73.1", "a" * 64, False, "k"))
    assert any(isinstance(h, nc.PinnedHTTPSHandler) for h in pinned.handlers)
    assert not any(isinstance(h, nc.ProxyHandler) and h.proxies for h in pinned.handlers)


@pytest.mark.parametrize("error,code,status", [
    (nc.PinMismatch(), "certificate_mismatch", 502),
    (URLError(ssl.SSLCertVerificationError("self signed")), "certificate_untrusted", 502),
    (URLError("refused"), "console_unreachable", 502),
    (TimeoutError(), "console_unreachable", 502),
    (ConnectionResetError(), "console_unreachable", 502),
])
def test_transport_errors_map_to_safe_codes(monkeypatch, config, error, code, status):
    class Opener:
        def open(self, req, timeout=None):
            raise error
    monkeypatch.setattr(nc, "opener_for", lambda config, server_name=None: Opener())
    with pytest.raises(nc.ConsoleError) as info:
        nc.request("/info", config=config)
    assert (info.value.code, info.value.status) == (code, status)
    assert "ephemeral-sentinel" not in str(info.value)


@pytest.mark.parametrize("http_status,code,status", [(401, "authentication_failed", 401), (403, "authentication_failed", 401),
                                                     (404, "upstream_http_error", 502), (500, "upstream_http_error", 502)])
def test_http_errors(monkeypatch, config, http_status, code, status):
    class Opener:
        def open(self, req, timeout=None):
            raise HTTPError(req.full_url, http_status, "x", Message(), io.BytesIO(b"{}"))
    monkeypatch.setattr(nc, "opener_for", lambda config, server_name=None: Opener())
    with pytest.raises(nc.ConsoleError) as info:
        nc.request("/info", config=config)
    assert (info.value.code, info.value.status) == (code, status)


def test_rate_limit_arms_cooldown_and_blocks_next_call(monkeypatch, config):
    calls = []

    class Opener:
        def open(self, req, timeout=None):
            calls.append(req)
            headers = Message()
            headers["Retry-After"] = "7"
            raise HTTPError(req.full_url, 429, "x", headers, io.BytesIO(b"{}"))
    monkeypatch.setattr(nc, "opener_for", lambda config, server_name=None: Opener())
    with pytest.raises(nc.ConsoleError) as first:
        nc.request("/info", config=config)
    assert first.value.retry_after == 7 and first.value.status == 429
    with pytest.raises(nc.ConsoleError) as second:
        nc.request("/info", config=config)
    assert second.value.code == "rate_limited" and len(calls) == 1


@pytest.mark.parametrize("body", [b"[]", b"null", b"not json", b"{" + b"a" * (nc.MAX_BYTES + 2) + b"}"])
def test_invalid_bodies(monkeypatch, config, body):
    class Opener:
        def open(self, req, timeout=None):
            return FakeResponse(body)
    monkeypatch.setattr(nc, "opener_for", lambda config, server_name=None: Opener())
    with pytest.raises(nc.ConsoleError) as info:
        nc.request("/info", config=config)
    assert info.value.code == "invalid_upstream_response"


def test_list_all_pages_until_total(monkeypatch, config):
    pages = []

    def fake_request(path, params=None, timeout=10, config=None):
        pages.append(params["offset"])
        start = params["offset"]
        rows = [{"id": str(i)} for i in range(start, min(start + nc.PAGE_LIMIT, 450))]
        return {"offset": start, "limit": nc.PAGE_LIMIT, "count": len(rows), "totalCount": 450, "data": rows}
    monkeypatch.setattr(nc, "request", fake_request)
    rows, partial = nc.list_all("/sites/x/clients", config)
    assert len(rows) == 450 and partial is False and pages == [0, 200, 400]


def test_list_all_caps_pages_and_reports_partial(monkeypatch, config):
    def fake_request(path, params=None, timeout=10, config=None):
        return {"offset": params["offset"], "limit": nc.PAGE_LIMIT, "count": nc.PAGE_LIMIT, "totalCount": 10 ** 6,
                "data": [{"id": "x"}] * nc.PAGE_LIMIT}
    monkeypatch.setattr(nc, "request", fake_request)
    rows, partial = nc.list_all("/sites/x/clients", config)
    assert len(rows) == nc.MAX_PAGES * nc.PAGE_LIMIT and partial is True


def test_list_all_rejects_non_object_rows(monkeypatch, config):
    monkeypatch.setattr(nc, "request", lambda *a, **k: {"data": ["x"]})
    with pytest.raises(nc.ConsoleError):
        nc.list_all("/sites/x/clients", config)


# ----------------------------------------------------------------------------- projections and privacy

def test_snapshot_hides_addresses_and_identifiers(fake_console, config, console_fixture):
    snap = nc.snapshot(config, now=NOW)
    text = json.dumps(snap)
    assert "ephemeral-sentinel" not in text
    for raw in console_fixture.values():
        for mac in ("02:00:00:aa:bb:01", "02:00:00:cc:dd:02"):
            assert mac not in text
    assert "10.99.0." not in text and "aaaaaaaa-0000" not in text and "cccccccc-0000" not in text
    assert "[address hidden]" in text and "[mac hidden]" in text
    assert snap["console"] == {"applicationVersion": "9.9.99", "siteName": "Synthetic Home", "siteHandle": "site-1"}
    assert [d["handle"] for d in snap["devices"]] == ["device-1", "device-2", "device-3"]
    assert snap["devices"][1]["uplinkHandle"] == "device-1"
    assert snap["devices"][1]["radios"][0]["txRetriesPct"] == 31.0
    assert snap["devices"][1]["stats"]["uptimeSec"] == 420
    assert snap["devices"][0]["ports"][1] == {"idx": 2, "state": "UP", "connector": "RJ45", "speedMbps": 100, "maxSpeedMbps": 1000, "poe": None}
    assert snap["clients"][2]["authorized"] is False and snap["clients"][1]["uplinkHandle"] == "device-3"
    assert snap["wifi"][1]["security"] == "OPEN" and snap["networks"][1]["vlanId"] == 50
    assert snap["partial"] is False and snap["errors"] == []
    assert all(d["ipAddress"] is None for d in snap["devices"]) and all(c["ipAddress"] is None for c in snap["clients"])


def test_snapshot_shows_addresses_only_when_enabled(fake_console, console_fixture):
    config = nc.Config("192.168.73.1", None, True, "ephemeral-sentinel")
    snap = nc.snapshot(config, now=NOW)
    assert snap["devices"][0]["ipAddress"] == "10.99.0.1" and snap["clients"][1]["ipAddress"] == "10.99.0.73"
    assert snap["devices"][2]["name"] == "Garage AP 10.99.0.3"
    assert snap["clients"][1]["name"] == "Phone [mac hidden]"
    assert "02:00:00" not in json.dumps(snap)


def test_snapshot_tolerates_section_failures(fake_console, config, console_fixture):
    del console_fixture["/sites/11111111-1111-4111-8111-111111111111/clients"]
    del console_fixture["/sites/11111111-1111-4111-8111-111111111111/devices/aaaaaaaa-0000-4000-8000-000000000002/statistics/latest"]
    snap = nc.snapshot(config, now=NOW)
    assert snap["partial"] is True
    assert {e["section"] for e in snap["errors"]} == {"clients", "device-statistics"}
    assert snap["clients"] == [] and snap["devices"][1]["stats"] is None and len(snap["devices"]) == 3


@pytest.mark.parametrize("code", ["authentication_failed", "certificate_mismatch", "certificate_untrusted", "rate_limited"])
def test_snapshot_fails_closed_on_trust_errors(monkeypatch, config, code):
    def fail(*args, **kwargs):
        raise nc.ConsoleError(code, 401 if code == "authentication_failed" else 502)
    monkeypatch.setattr(nc, "request", fail)
    with pytest.raises(nc.ConsoleError) as info:
        nc.snapshot(config, now=NOW)
    assert info.value.code == code


def test_snapshot_without_site_is_partial(monkeypatch, config):
    monkeypatch.setattr(nc, "request", lambda path, params=None, timeout=10, config=None: {"applicationVersion": "1"} if path == "/info" else {"data": [], "totalCount": 0})
    snap = nc.snapshot(config, now=NOW)
    assert snap["partial"] is True and snap["devices"] == [] and snap["errors"][0]["section"] == "sites"


def test_handles_are_opaque_and_stable_within_process():
    first = nc.handle("device", "abc")
    assert first == nc.handle("device", "abc") and first.startswith("device-")
    assert nc.resolve(first) == ("device", "abc") and nc.resolve("nope") is None
    assert nc.handle("device", None) is None and nc.handle("device", "") is None


def test_clean_text_redacts_and_bounds(config):
    assert nc.clean_text("AP 192.168.1.5 aa:bb:cc:dd:ee:ff", config) == "AP [address hidden] [mac hidden]"
    assert nc.clean_text("fe80::1 link", config) == "[address hidden] link"
    assert nc.clean_text("x" * 500, config) == "x" * 160
    assert nc.clean_text("key ephemeral-sentinel", config) is None
    assert nc.clean_text(12, config) is None and nc.clean_text("\x00\x01", config) is None
    assert nc.enum("WPA2_PERSONAL") == "WPA2_PERSONAL" and nc.enum("drop table") is None
    assert nc.number(-1) is None and nc.number(float("nan")) is None and nc.number(0) == 0
    assert nc.stamp("2026-11-14T12:00:00Z") == "2026-11-14T12:00:00+00:00" and nc.stamp("2026-11-14T12:00:00") is None


# ----------------------------------------------------------------------------- DNS rebinding and write impossibility

def test_resolve_private_accepts_private_literal(config):
    assert nc.resolve_private(config) == ("192.168.73.1", 443, None)
    assert nc.resolve_private(nc.Config("192.168.73.1:8443", None, False, "k")) == ("192.168.73.1", 8443, None)
    assert nc.resolve_private(nc.Config("[fd00::1]", None, False, "k")) == ("[fd00::1]", 443, None)


def test_resolve_private_pins_the_resolved_address(config):
    host, port, server_name = nc.resolve_private(nc.Config("unifi.local", None, False, "k"))
    assert host.startswith("192.168.73.") and port == 443 and server_name == "unifi.local"


@pytest.mark.parametrize("answers,code", [
    (["8.8.8.8"], "invalid_console_host"),
    (["192.168.73.5", "8.8.4.4"], "invalid_console_host"),   # any public answer poisons the name
    (["127.0.0.1"], "invalid_console_host"),
    (["::"], "invalid_console_host"),
    ([], "console_unreachable"),
])
def test_resolve_private_defeats_rebinding(monkeypatch, code, answers):
    monkeypatch.setattr(nc.socket, "getaddrinfo", lambda h, p, **k: [(2, 1, 6, "", (a, p)) for a in answers])
    with pytest.raises(nc.ConsoleError) as info:
        nc.resolve_private(nc.Config("unifi.local", None, False, "k"))
    assert info.value.code == code


def test_resolve_private_maps_dns_failure(monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("no such host")
    monkeypatch.setattr(nc.socket, "getaddrinfo", boom)
    with pytest.raises(nc.ConsoleError) as info:
        nc.resolve_private(nc.Config("unifi.local", None, False, "k"))
    assert info.value.code == "console_unreachable"


def test_hostname_request_uses_validated_ip_and_keeps_host_header(monkeypatch):
    seen = []

    class Opener:
        def open(self, req, timeout=None):
            seen.append(req)
            raise nc.ConsoleError("console_unreachable", 502)
    monkeypatch.setattr(nc, "opener_for", lambda config, server_name=None: Opener())
    with pytest.raises(nc.ConsoleError):
        nc.request("/info", config=nc.Config("unifi.local:8443", None, False, "k"))
    url = seen[0].full_url
    assert "unifi.local" not in url and url.startswith("https://192.168.73.") and ":8443" in url
    assert seen[0].get_header("Host") == "unifi.local:8443"


def test_client_cannot_issue_write_methods():
    import re
    from pathlib import Path
    source = Path(nc.__file__).read_text()
    assert 'method="GET"' in source
    assert not re.search(r'method\s*=\s*[\'"]\s*(POST|PUT|PATCH|DELETE)\b', source, re.I)
    assert not re.search(r'\.(post|put|patch|delete)\s*\(', source, re.I)
    assert not re.search(r"\breq(uests)?\.(post|put|patch|delete)\b", source, re.I)
