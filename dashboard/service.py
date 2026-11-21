"""Shared read-only service used by both the dashboard routes and the agent tools.

Deliberately free of FastAPI (and of any framework import): the agent tools load this
directly so a broken or absent web stack cannot break tool calls.
"""
import importlib.util
import sys
import threading
import time
from pathlib import Path

SNAPSHOT_MAX_AGE = 30.0
EMPTY_SNAPSHOT = {"devices": [], "clients": [], "wans": [], "networks": [], "wifi": [], "partial": True, "errors": []}


def _load(stem):
    name = f"{__name__}_{stem}"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(f"{stem}.py"))
    if spec is None or spec.loader is None:
        raise ImportError(stem)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


client = _load("unifi_client")
console = _load("network_client")
diagnostics = _load("diagnostics")
_cache = {"at": 0.0, "snapshot": None}
_lock = threading.Lock()


def cached_snapshot(max_age=SNAPSHOT_MAX_AGE):
    """One bounded console read serves every view for a short window; a refresh after the window re-reads."""
    with _lock:
        if _cache["snapshot"] is not None and time.monotonic() - _cache["at"] < max_age:
            return _cache["snapshot"]
        snapshot = console.snapshot()
        _cache["at"], _cache["snapshot"] = time.monotonic(), snapshot
        return snapshot


def cloud_configured():
    try:
        client.load_key()
        return True
    except client.SafeError:
        return False


def cloud_isp_items():
    try:
        return client.view_data("isp")["items"]
    except (client.SafeError, KeyError, TypeError):
        return None


def diagnostics_report():
    """Console + cloud findings. Never raises for a missing source; only console trust errors propagate."""
    configured, code = console.configured()
    snapshot = cached_snapshot() if configured else {**EMPTY_SNAPSHOT, "console": {"configured": False, "code": code}}
    cloud = cloud_configured()
    report = diagnostics.analyze(snapshot, cloud_isp_items() if cloud else None, console_configured=configured)
    report["sources"] = {"console": configured, "consoleCode": code, "cloud": cloud}
    return report


def section(name):
    snapshot = cached_snapshot()
    items = snapshot[name]
    if name == "clients":
        names = {d["handle"]: d.get("name") for d in snapshot["devices"]}
        items = [{**c, "uplinkName": names.get(c.get("uplinkHandle"))} for c in items]
    return {"items": items, "partial": snapshot["partial"], "errors": snapshot["errors"],
            "console": snapshot["console"], "generatedAt": snapshot["generatedAt"]}


def cloud_view(view):
    return client.overview_data() if view == "overview" else client.view_data(view)


def console_configured():
    return console.configured()
