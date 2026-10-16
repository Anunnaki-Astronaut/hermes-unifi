"""Fixed native dashboard API; no caller-controlled upstream arguments."""
import importlib.util
import sys
from pathlib import Path
from fastapi import APIRouter, HTTPException

_name = f"{__name__}_unifi_client"
_spec = importlib.util.spec_from_file_location(_name, Path(__file__).with_name("unifi_client.py"))
client = importlib.util.module_from_spec(_spec)
sys.modules[_name] = client
_spec.loader.exec_module(client)
router = APIRouter()


def run(view):
    try:
        return {"ok": True, "data": client.overview_data() if view == "overview" else client.view_data(view)}
    except client.SafeError as exc:
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after is not None else None
        raise HTTPException(exc.status, detail={"code": exc.code, "message": exc.message}, headers=headers) from None


@router.get("/health")
def health():
    try:
        client.load_key()
        configured = True
    except client.SafeError:
        configured = False
    return {"ok": True, "configured": configured, "connected": None,
            "read_only": True, "version": "0.1.0"}


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
