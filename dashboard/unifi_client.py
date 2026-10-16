"""Fixed Site Manager GET transport and explicit renderer projections."""
from __future__ import annotations

import importlib
import json
import math
import os
import re
import ssl
import time
from http.client import HTTPException as TransportError
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, HTTPSHandler, HTTPRedirectHandler, ProxyHandler, build_opener

ORIGIN = "https://api.ui.com/v1"
ENDPOINTS = {"sites": "/sites", "devices": "/devices", "isp": "/isp-metrics/5m"}
MAX_BYTES = 5 * 1024 * 1024
_retry_until = 0.0
MESSAGES = {
    "not_configured": "Configure the profile-scoped UniFi API key in plugin settings.",
    "authentication_failed": "UniFi authentication failed.",
    "rate_limited": "UniFi rate limit reached.",
    "upstream_http_error": "UniFi returned an HTTP error.",
    "unifi_unreachable": "UniFi could not be reached.",
    "invalid_upstream_response": "UniFi returned an invalid response.",
}


class SafeError(Exception):
    def __init__(self, code, status=502, retry_after=None):
        self.code, self.status, self.retry_after = code, status, retry_after
        self.message = MESSAGES[code]
        super().__init__(self.message)


def load_key(settings=None):
    # Settings deliberately ignored. Only absence of the module permits env use.
    try:
        scope = importlib.import_module("agent.secret_scope")
    except ModuleNotFoundError as exc:
        if exc.name not in {"agent", "agent.secret_scope"}:
            raise SafeError("not_configured", 503) from None
        value = os.environ.get("UNIFI_API_KEY")
    except Exception:
        raise SafeError("not_configured", 503) from None
    else:
        try:
            value = scope.get_secret("UNIFI_API_KEY", None)
        except Exception:
            raise SafeError("not_configured", 503) from None
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 33 or ord(c) > 126 for c in value):
        raise SafeError("not_configured", 503)
    return value


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def retry_seconds(value):
    # Bound raw length and precision before parsing; allow surrounding HTTP whitespace.
    if not isinstance(value, str) or len(value) > 32:
        return None
    value = value.strip(' \t')
    if not re.fullmatch(r"[0-9]{1,6}(?:\.[0-9]{1,6})?", value):
        return None
    whole, _, fraction = value.partition('.')
    # Exact ceiling avoids rounding a positive fraction down to an integer.
    return min(int(whole) + int(any(digit != '0' for digit in fraction)), 86400)


def request_data(view, timeout=10):
    global _retry_until
    if view not in ENDPOINTS:
        raise ValueError("Unsupported view")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= timeout <= 30:
        raise ValueError("Timeout must be between 1 and 30 seconds")
    key = load_key()
    remaining = math.ceil(_retry_until - time.monotonic())
    if remaining > 0:
        raise SafeError("rate_limited", 429, remaining)
    req = Request(ORIGIN + ENDPOINTS[view], headers={"X-API-KEY": key, "Accept": "application/json", "User-Agent": "Hermes-UniFi/0.1.0"}, method="GET")
    try:
        # No environment proxies, redirect forwarding, or configurable TLS context.
        opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
        with opener.open(req, timeout=timeout) as response:
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise SafeError("invalid_upstream_response")
        payload = json.loads(raw)
        if (not isinstance(payload, dict) or type(payload.get("httpStatusCode")) is not int
                or payload["httpStatusCode"] != 200 or not isinstance(payload.get("traceId"), str)
                or not isinstance(payload.get("data"), list)
                or any(not isinstance(row, dict) for row in payload["data"])):
            raise SafeError("invalid_upstream_response")
        # Never project the envelope, trace, token, or key into renderer output.
        return payload["data"], bool(payload.get("nextToken")), key
    except HTTPError as exc:
        status = exc.code
        retry = retry_seconds(exc.headers.get("Retry-After")) if exc.headers else None
        exc.close()
        if status == 429 and retry is not None:
            _retry_until = max(_retry_until, time.monotonic() + retry)
        code = "authentication_failed" if status in (401, 403) else "rate_limited" if status == 429 else "upstream_http_error"
        raise SafeError(code, 401 if status in (401, 403) else 429 if status == 429 else 502, retry if status == 429 else None) from None
    except (URLError, OSError, TimeoutError, TransportError):
        raise SafeError("unifi_unreachable") from None
    except (ValueError, TypeError, RecursionError):
        raise SafeError("invalid_upstream_response") from None


def obj(value):
    return value if isinstance(value, dict) else {}


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def text(value, key, identifiers=()):
    if not isinstance(value, str):
        return None
    # Names may themselves contain addresses or identifiers. Fail closed there too.
    if key in value or any(i and i in value for i in identifiers):
        return None
    if re.search(r"(?:\d{1,3}\.){3}\d{1,3}|(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}|[0-9a-f]{12,}|[0-9a-f]{0,4}:[0-9a-f:]*:[0-9a-f:]*", value, re.I):
        return None
    return ''.join(c for c in value if c.isprintable())[:160]


def identifiers(rows):
    found = []
    def visit(v):
        if isinstance(v, dict):
            for k, x in v.items():
                if k.lower() in {"id", "siteid", "hostid", "mac", "ip", "guid", "hardwareid", "traceid"} and isinstance(x, str):
                    found.append(x)
                else:
                    visit(x)
        elif isinstance(v, list):
            for x in v:
                visit(x)
    visit(rows)
    return found


def project(view, rows, key):
    ids = identifiers(rows)
    clean = lambda v: text(v, key, ids)
    result = []
    if view == "sites":
        for row in rows:
            meta, stats = obj(row.get("meta")), obj(row.get("statistics"))
            counts = obj(stats.get("counts"))
            result.append({"name": clean(meta.get("name")), "description": clean(meta.get("desc")),
                           "timezone": clean(meta.get("timezone")),
                           "totalDevices": number(counts.get("totalDevice")),
                           "offlineDevices": number(counts.get("offlineDevice")),
                           "pendingUpdates": number(counts.get("pendingUpdateDevice")),
                           "wanUptime": number(obj(stats.get("percentages")).get("wanUptime"))})
    elif view == "devices":
        for row in rows:
            devices = row.get("devices")
            if not isinstance(devices, list) or any(not isinstance(d, dict) for d in devices):
                raise SafeError("invalid_upstream_response")
            for device in devices:
                result.append({k: clean(device.get(k)) for k in
                               ("name", "model", "productLine", "status", "version", "firmwareStatus", "updateAvailable")})
    else:
        latest = {}
        for row in rows:
            if row.get("metricType") != "5m" or not isinstance(row.get("periods"), list):
                raise SafeError("invalid_upstream_response")
            pair = (row.get("hostId"), row.get("siteId"))
            if not all(isinstance(v, str) for v in pair):
                raise SafeError("invalid_upstream_response")
            for period in row["periods"]:
                try:
                    stamp = datetime.fromisoformat(period["metricTime"].replace("Z", "+00:00"))
                    if stamp.tzinfo is None:
                        raise ValueError()
                except (KeyError, ValueError, TypeError, AttributeError):
                    raise SafeError("invalid_upstream_response") from None
                if pair not in latest or stamp > latest[pair][0]:
                    latest[pair] = (stamp, period)
        for index, (stamp, period) in enumerate(latest.values(), 1):
            wan = obj(obj(period.get("data")).get("wan"))
            result.append({"label": f"Site / host {index}", "metricTime": stamp.astimezone(timezone.utc).isoformat(),
                           "ispName": clean(wan.get("ispName")),
                           **{k: number(wan.get(k)) for k in ("avgLatency", "maxLatency", "download_kbps", "upload_kbps", "downtime", "packetLoss", "uptime")}})
    return result


def view_data(view):
    rows, truncated, key = request_data(view)
    items = project(view, rows, key)
    degraded = any((r.get("offlineDevices") or 0) > 0 or (r.get("pendingUpdates") or 0) > 0
                   or (r.get("wanUptime") is not None and r["wanUptime"] < 100)
                   or (r.get("status") not in (None, "online"))
                   or (r.get("packetLoss") or 0) > 0 or (r.get("downtime") or 0) > 0 for r in items)
    return {"items": items, "partial": truncated, "degraded": degraded,
            "notice": "Only the first upstream page is shown." if truncated else None}


def overview_data():
    summaries, errors = {}, []
    first_error = None
    for view in ENDPOINTS:
        try:
            data = view_data(view)
            summaries[view] = {"count": len(data["items"]), "degraded": data["degraded"], "partial": data["partial"]}
        except SafeError as exc:
            if exc.code == "not_configured":
                raise
            if first_error is None:
                first_error = exc
            errors.append({"view": view, "code": exc.code, "message": exc.message})
    if not summaries:
        raise first_error
    return {"summaries": summaries, "errors": errors,
            "partial": bool(errors) or any(s["partial"] for s in summaries.values()),
            "degraded": bool(errors) or any(s["degraded"] for s in summaries.values())}
