"""Agent tool handlers. Every handler accepts ``(args, **kwargs)``, returns a JSON string, never raises,
and never performs anything but bounded GET reads through the dashboard modules."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

QUERY_LIMIT = 80
FOCUS_CATEGORIES = {
    "all": None, "devices": {"devices"}, "wifi": {"wifi"}, "wired": {"wired"}, "internet": {"internet"},
    "clients": {"clients"}, "security": {"security"}, "firmware": {"firmware"}, "resources": {"resources"},
    "stability": {"stability"},
}


def _load(stem):
    name = f"hermes_unifi_tools_{stem}"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / "dashboard" / f"{stem}.py")
    if spec is None or spec.loader is None:
        raise ImportError(stem)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _service():
    """Load the framework-free service module; agent tools must not depend on the web stack."""
    return _load("service")


def _error(code, message, status=None):
    return json.dumps({"ok": False, "read_only": True, "code": code, "message": message, "status": status})


def _query(args):
    value = args.get("query") if isinstance(args, dict) else None
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("query must be text")
    cleaned = "".join(c for c in value if c.isprintable()).strip().lower()
    if len(cleaned) > QUERY_LIMIT:
        raise ValueError(f"query must be at most {QUERY_LIMIT} characters")
    return cleaned or None


def _matches(item, query):
    if query is None:
        return True
    return any(isinstance(item.get(k), str) and query in item[k].lower() for k in ("name", "model", "type", "handle"))


def _guard(fn):
    def wrapped(args=None, **kwargs):
        service = _service()
        try:
            return json.dumps(fn(_service(), args if isinstance(args, dict) else {}))
        except ValueError as exc:
            return _error("invalid_input", str(exc))
        except service.console.ConsoleError as exc:
            return _error(exc.code, exc.message, exc.status)
        except service.client.SafeError as exc:
            return _error(exc.code, exc.message, exc.status)
        except Exception:  # Never let a surprise reach the agent loop; never echo internals.
            return _error("internal_error", "The UniFi plugin hit an unexpected error while reading data.")
    wrapped.__name__ = fn.__name__
    return wrapped


@_guard
def unifi_status(service, args):
    report = service.diagnostics_report()
    counts = report["summary"]
    down = [f["subject"]["name"] for f in report["findings"] if f["id"].startswith("device-down:") and f.get("subject")]
    if report["sources"]["console"]:
        sentence = (f"{report['deviceCount']} UniFi device{'s' if report['deviceCount'] != 1 else ''} and "
                    f"{report['clientCount']} connected client{'s' if report['clientCount'] != 1 else ''} checked. "
                    f"{report['headline']}.")
        if down:
            sentence += f" Down: {', '.join(down)}."
    else:
        sentence = ("The local UniFi console is not connected, so devices, clients, Wi-Fi, and ports were not checked. "
                    f"Cloud check: {report['headline'].lower()}.")
    return {"ok": True, "read_only": True, "summary": sentence, "headline": report["headline"], "counts": counts,
            "deviceCount": report["deviceCount"], "clientCount": report["clientCount"], "sources": report["sources"],
            "generatedAt": report["generatedAt"]}


@_guard
def unifi_diagnose(service, args):
    focus = args.get("focus", "all")
    if focus not in FOCUS_CATEGORIES:
        raise ValueError(f"focus must be one of {', '.join(FOCUS_CATEGORIES)}")
    report = service.diagnostics_report()
    categories = FOCUS_CATEGORIES[focus]
    findings = [f for f in report["findings"] if categories is None or f["category"] in categories]
    text = service.diagnostics.plain_text({**report, "findings": findings}) if findings else \
        f"No findings in the '{focus}' area. Overall: {report['headline']}."
    return {"ok": True, "read_only": True, "focus": focus, "headline": report["headline"], "summary": report["summary"],
            "findings": findings, "plain_text": text, "sources": report["sources"], "generatedAt": report["generatedAt"],
            "note": "Fixes are described, not executed. Apply changes in the UniFi console."}


def _device_row(device):
    stats = device.get("stats") or {}
    return {"handle": device.get("handle"), "name": device.get("name"), "model": device.get("model"), "state": device.get("state"),
            "firmwareVersion": device.get("firmwareVersion"), "firmwareUpdatable": device.get("firmwareUpdatable"),
            "supported": device.get("supported"), "ipAddress": device.get("ipAddress"), "features": device.get("features"),
            "uplinkHandle": device.get("uplinkHandle"), "uptimeSec": stats.get("uptimeSec"),
            "cpuUtilizationPct": stats.get("cpuUtilizationPct"), "memoryUtilizationPct": stats.get("memoryUtilizationPct"),
            "radios": [{k: r.get(k) for k in ("frequencyGHz", "channel", "channelWidthMHz", "txPowerMode", "txRetriesPct")}
                       for r in device.get("radios") or []],
            "ports": [{k: p.get(k) for k in ("idx", "state", "speedMbps", "maxSpeedMbps")} | {"poe": (p.get("poe") or {}).get("state")}
                      for p in device.get("ports") or [] if p.get("state") == "UP"]}


@_guard
def unifi_devices(service, args):
    query = _query(args)
    snapshot = service.cached_snapshot()
    items = [_device_row(d) for d in snapshot["devices"] if _matches(d, query)]
    return {"ok": True, "read_only": True, "query": query, "count": len(items), "items": items, "partial": snapshot["partial"],
            "errors": snapshot["errors"], "generatedAt": snapshot["generatedAt"],
            "note": "Handles like device-2 are temporary labels for this process, not identities."}


@_guard
def unifi_clients(service, args):
    query = _query(args)
    snapshot = service.cached_snapshot()
    names = {d["handle"]: d.get("name") for d in snapshot["devices"]}
    items = [{**c, "uplinkName": names.get(c.get("uplinkHandle"))} for c in snapshot["clients"] if _matches(c, query)]
    return {"ok": True, "read_only": True, "query": query, "count": len(items), "items": items, "partial": snapshot["partial"],
            "errors": snapshot["errors"], "generatedAt": snapshot["generatedAt"],
            "note": "MAC addresses are never returned. IP addresses appear only when enabled in plugin settings."}


HANDLERS = {"unifi_status": unifi_status, "unifi_diagnose": unifi_diagnose, "unifi_devices": unifi_devices, "unifi_clients": unifi_clients}
