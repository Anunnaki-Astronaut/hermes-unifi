"""Fixed native dashboard API; no caller-controlled upstream arguments, GET only, read only.

Read logic lives in ``service.py`` so the agent tools can share it without importing FastAPI.
"""
import importlib.util
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

VERSION = "0.3.0"


def _load(stem):
    name = f"{__name__}_{stem}"
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(f"{stem}.py"))
    if spec is None or spec.loader is None:
        raise ImportError(stem)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


service = _load("service")
client, console, diagnostics = service.client, service.console, service.diagnostics
router = APIRouter()
_cache = service._cache
SNAPSHOT_MAX_AGE = service.SNAPSHOT_MAX_AGE
cached_snapshot = service.cached_snapshot
diagnostics_report = service.diagnostics_report
cloud_configured = service.cloud_configured


def _http(exc):
    headers = {"Retry-After": str(exc.retry_after)} if getattr(exc, "retry_after", None) is not None else None
    return HTTPException(exc.status, detail={"code": exc.code, "message": exc.message}, headers=headers)


def run(view):
    try:
        return {"ok": True, "data": service.cloud_view(view)}
    except client.SafeError as exc:
        raise _http(exc) from None


def console_run(fn):
    try:
        return {"ok": True, "data": fn()}
    except console.ConsoleError as exc:
        raise _http(exc) from None


@router.get("/health")
def health():
    console_ok, code = service.console_configured()
    return {"ok": True, "configured": service.cloud_configured(), "connected": None, "read_only": True, "version": VERSION,
            "console": {"configured": console_ok, "code": code}}


@router.get("/overview")
def overview():
    return run("overview")


@router.get("/sites")
def sites():
    return run("sites")


@router.get("/devices")
def devices():
    return run("devices")


@router.get("/isp")
def isp():
    return run("isp")


@router.get("/console/health")
def console_health():
    configured, code = service.console_configured()
    return {"ok": True, "configured": configured, "code": code, "read_only": True}


@router.get("/console/fingerprint")
def console_fingerprint():
    return console_run(console.peek_certificate)


@router.get("/console/devices")
def console_devices():
    return console_run(lambda: service.section("devices"))


@router.get("/console/clients")
def console_clients():
    return console_run(lambda: service.section("clients"))


@router.get("/console/wifi")
def console_wifi():
    return console_run(lambda: service.section("wifi"))


@router.get("/console/networks")
def console_networks():
    return console_run(lambda: service.section("networks"))


@router.get("/diagnostics")
def diagnostics_view():
    return console_run(service.diagnostics_report)


@router.get("/report")
def report_view():
    return console_run(lambda: {"text": diagnostics.plain_text(service.diagnostics_report())})
