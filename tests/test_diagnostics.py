"""Diagnostics engine: deterministic findings, plain English, no network."""
import json
from datetime import datetime, timezone

import pytest

from conftest import console as nc, diagnostics as dx, console_fixture, FakeResponse

NOW = datetime(2026, 11, 14, 12, 0, 30, tzinfo=timezone.utc)


def device(**overrides):
    base = {"handle": "device-9", "name": "Test AP", "model": "U6", "state": "ONLINE", "supported": True,
            "firmwareVersion": "1.0", "firmwareUpdatable": False, "ipAddress": None, "features": ["accessPoint"],
            "uplinkHandle": None, "ports": [], "radios": [], "stats": None}
    base.update(overrides)
    return base


def report(**snapshot):
    base = {"console": {}, "devices": [], "clients": [], "wans": [{"handle": "wan-1", "name": "Internet"}], "networks": [], "wifi": [],
            "partial": False, "errors": []}
    base.update(snapshot)
    return dx.analyze(base, now=NOW)


def ids(result):
    return [f["id"].split(":")[0] for f in result["findings"]]


@pytest.fixture
def snapshot(monkeypatch, console_fixture):
    class Opener:
        def open(self, req, timeout=None):
            path = req.full_url.split("/integration/v1", 1)[1].split("?", 1)[0]
            body = json.dumps(console_fixture[path]).encode()
            return FakeResponse(body)
    monkeypatch.setattr(nc, "opener_for", lambda config, server_name=None: Opener())
    return nc.snapshot(nc.Config("192.168.73.1", None, False, "ephemeral-sentinel"), now=NOW)


def test_fixture_report_is_plain_english_and_ordered(snapshot):
    result = dx.analyze(snapshot, now=NOW)
    severities = [f["severity"] for f in result["findings"]]
    assert severities == sorted(severities, key=dx.SEVERITY_ORDER.__getitem__)
    titles = {f["id"]: f["title"] for f in result["findings"]}
    assert titles["device-down:device-3"] == "Garage AP [address hidden] is offline"
    assert titles["cpu-high:device-1"] == "Gateway synthetic-host CPU is at 92%"
    assert titles["firmware-available:device-1"] == "Firmware update available for Gateway synthetic-host"
    assert titles["radio-retries:device-2"] == "High Wi-Fi retry rate on Office AP (2.4 GHz)"
    assert titles["width-2g:device-2"] == "Office AP uses 40 MHz on 2.4 GHz"
    assert titles["channel-2g:device-2"] == "Office AP is on 2.4 GHz channel 3"
    assert titles["port-slow:device-1"] == "Port 2 on Gateway synthetic-host linked at 100 Mbps"
    assert titles["poe-limited:device-1"] == "PoE is limited on port 4 of Gateway synthetic-host"
    assert titles["device-unsupported:device-3"] == "Garage AP [address hidden] is not fully supported"
    assert titles["recent-restart:device-2"] == "Office AP restarted 7 minutes ago"
    assert titles["wifi-open:wifi-2"] == "Wi-Fi network Guest-Synthetic has no encryption"
    assert titles["wifi-disabled:wifi-3"] == "Wi-Fi network Old-IoT is disabled"
    assert titles["clients-summary:site"] == "3 clients connected"
    assert titles["clients-unauthorized:site"] == "1 guest client waiting for authorization"
    assert titles["clients-stranded:site"] == "1 client last seen on a device that is down"
    assert result["summary"]["critical"] == 2 and result["headline"].startswith("2 critical problems, ")
    assert result["readOnly"] is True and result["deviceCount"] == 3 and result["clientCount"] == 3
    assert "all-clear" not in ids(result) and "channel-overlap" not in ids(result)
    assert "coverage-partial" not in ids(result)
    text = json.dumps(result)
    assert "ephemeral-sentinel" not in text and "10.99.0" not in text and "aaaaaaaa-0000" not in text


def test_fixes_are_proposed_but_unavailable(snapshot):
    result = dx.analyze(snapshot, now=NOW)
    fixes = {f["id"]: f["fix"] for f in result["findings"] if f["fix"]}
    assert fixes["device-down:device-3"] == {"action": "RESTART_DEVICE", "target": "device-3", "arguments": {}, "available": False,
                                              "requiresApproval": True, "reason": dx.WRITES_UNAVAILABLE}
    assert fixes["poe-limited:device-1"]["action"] == "POWER_CYCLE_PORT" and fixes["poe-limited:device-1"]["arguments"] == {"portIdx": 4}
    assert all(f["available"] is False and f["requiresApproval"] is True for f in fixes.values())


def test_all_clear_when_nothing_is_wrong():
    result = report(devices=[device()])
    assert ids(result) == ["all-clear"] and result["headline"] == "Network looks healthy"
    assert result["findings"][0]["detail"] == "1 device checked; nothing needs attention right now."


@pytest.mark.parametrize("state,rule,severity", [
    ("OFFLINE", "device-down", "critical"), ("CONNECTION_INTERRUPTED", "device-down", "critical"), ("ISOLATED", "device-down", "critical"),
    ("UPDATING", "device-transition", "info"), ("ADOPTING", "device-transition", "info"), ("PENDING_ADOPTION", "device-transition", "info"),
    ("U5G_INCORRECT_TOPOLOGY", "device-topology", "warning"), (None, "device-state-unknown", "info"),
])
def test_device_state_rules(state, rule, severity):
    result = report(devices=[device(state=state)])
    match = [f for f in result["findings"] if f["id"].startswith(rule)]
    assert len(match) == 1 and match[0]["severity"] == severity
    assert match[0]["subject"] == {"handle": "device-9", "name": "Test AP"}


@pytest.mark.parametrize("cpu,memory,expected", [
    (95, 10, {"cpu-high"}), (80, 10, {"cpu-elevated"}), (50, 95, {"memory-high"}), (95, 95, {"cpu-high", "memory-high"}), (10, 10, set()),
])
def test_resource_rules(cpu, memory, expected):
    result = report(devices=[device(stats={"cpuUtilizationPct": cpu, "memoryUtilizationPct": memory})])
    assert {i for i in ids(result) if i in {"cpu-high", "cpu-elevated", "memory-high"}} == expected


def test_heartbeat_late_only_when_online_and_overdue():
    late = device(stats={"nextHeartbeatAt": "2026-11-14T11:50:00+00:00"})
    assert "heartbeat-late" in ids(report(devices=[late]))
    assert "heartbeat-late" not in ids(report(devices=[device(stats={"nextHeartbeatAt": "2026-11-14T12:00:00+00:00"})]))
    assert "heartbeat-late" not in ids(report(devices=[device(state="OFFLINE", stats={"nextHeartbeatAt": "2026-11-14T11:00:00+00:00"})]))


@pytest.mark.parametrize("retries,severity", [(60, "critical"), (30, "warning"), (10, None)])
def test_radio_retry_thresholds(retries, severity):
    result = report(devices=[device(radios=[{"frequencyGHz": 5, "channel": 36, "channelWidthMHz": 80, "txPowerMode": "AUTO", "wlanStandard": "802.11ax", "txRetriesPct": retries}])])
    match = [f for f in result["findings"] if f["id"].startswith("radio-retries")]
    assert ([m["severity"] for m in match] == [severity]) if severity else match == []
    if match:
        assert "(5 GHz)" in match[0]["title"]


def test_channel_overlap_counts_only_online_devices():
    radio = {"frequencyGHz": 5, "channel": 44, "channelWidthMHz": 80, "txPowerMode": "AUTO", "wlanStandard": "802.11ax", "txRetriesPct": None}
    online = [device(handle="device-1", name="A", radios=[radio]), device(handle="device-2", name="B", radios=[dict(radio)])]
    result = report(devices=online)
    overlap = [f for f in result["findings"] if f["id"] == "channel-overlap:site"]
    assert overlap and overlap[0]["title"] == "2 access points share 5 GHz channel 44"
    assert overlap[0]["evidence"]["devices"] == ["device-1", "device-2"]
    online[1]["state"] = "OFFLINE"
    assert "channel-overlap" not in ids(report(devices=online))


@pytest.mark.parametrize("speed,maximum,state,expected", [(100, 1000, "UP", True), (10, 1000, "UP", True), (1000, 1000, "UP", False),
                                                           (100, 100, "UP", False), (100, 1000, "DOWN", False), (None, 1000, "UP", False)])
def test_port_speed_rule(speed, maximum, state, expected):
    result = report(devices=[device(ports=[{"idx": 7, "state": state, "connector": "RJ45", "speedMbps": speed, "maxSpeedMbps": maximum, "poe": None}])])
    assert ("port-slow" in ids(result)) is expected


def test_wifi_rules():
    wifi = [{"handle": "wifi-1", "name": "Open", "enabled": True, "security": "OPEN"},
            {"handle": "wifi-2", "name": "Old", "enabled": True, "security": "WPA2_PERSONAL"},
            {"handle": "wifi-3", "name": "Off", "enabled": False, "security": "OPEN"},
            {"handle": "wifi-4", "name": "Good", "enabled": True, "security": "WPA3_PERSONAL"}]
    result = report(wifi=wifi)
    assert {f["id"] for f in result["findings"] if f["category"] in ("security", "wifi")} == {"wifi-open:wifi-1", "wifi-wpa2-only:wifi-2", "wifi-disabled:wifi-3"}


def test_wan_and_isp_rules():
    assert "wan-missing" in ids(report(wans=[]))
    isp = [{"label": "Site / host 1", "ispName": "Synthetic ISP", "packetLoss": 2, "downtime": 30, "avgLatency": 140, "metricTime": "2026-11-14T11:55:00+00:00"}]
    result = dx.analyze({"devices": [], "clients": [], "wans": [{"handle": "wan-1", "name": "x"}], "wifi": []}, cloud_isp=isp, now=NOW)
    titles = {f["id"]: f["title"] for f in result["findings"]}
    assert titles["isp-packet-loss:site"] == "Packet loss on Synthetic ISP"
    assert titles["isp-downtime:site"] == "Internet downtime on Synthetic ISP"
    assert titles["isp-latency:site"] == "High latency on Synthetic ISP"
    assert " ms" not in json.dumps(result)  # units stay unlabeled, as in the ISP view


def test_coverage_note_for_partial_snapshots():
    result = report(partial=True, errors=[{"section": "clients", "code": "console_unreachable", "message": "x"}])
    match = [f for f in result["findings"] if f["id"] == "coverage-partial:site"]
    assert match and "(clients)" in match[0]["detail"]


def test_plain_text_report(snapshot):
    text = dx.plain_text(dx.analyze(snapshot, now=NOW))
    assert text.startswith("UniFi network check — 2 critical problems, ")
    assert "\nCritical:\n- Garage AP [address hidden] is offline." in text
    assert "  What to do: Check its power or PoE source" in text
    assert "Warnings:" in text and "Notes:" in text and "OK:" in text
    assert "What to do: No action needed." not in text
    assert "ephemeral-sentinel" not in text and "10.99.0" not in text


def test_headline_grammar():
    assert dx.headline({"critical": 1, "warning": 1, "info": 1}) == "1 critical problem, 1 warning, 1 note"
    assert dx.headline({"critical": 0, "warning": 2, "info": 0}) == "2 warnings"
    assert dx.headline({}) == "Network looks healthy"


def test_unconfigured_console_reports_only_a_setup_note():
    result = dx.analyze({"devices": [], "clients": [], "wans": [], "wifi": [], "partial": True, "errors": []},
                        console_configured=False, now=NOW)
    ids = [f["id"] for f in result["findings"]]
    assert ids == ["console-not-connected:site"]
    assert result["consoleConnected"] is False and result["deviceCount"] == 0
    assert "devices, clients, Wi-Fi, ports, and internet health" in result["findings"][0]["detail"]
    assert "Network API key" in result["findings"][0]["recommendation"]
    assert "all-clear" not in ids and "wan-missing" not in ids and "coverage-partial" not in ids


def test_configured_console_still_flags_missing_wan():
    result = dx.analyze({"devices": [], "clients": [], "wans": [], "wifi": [], "partial": False, "errors": []}, now=NOW)
    assert "wan-missing:site" in [f["id"] for f in result["findings"]]
    assert result["consoleConnected"] is True
