"""Local UniFi Network Integration API client.

Fixed private console host, GET-only, bounded reads, pinned-or-CA-verified TLS,
and privacy projections that never expose MAC addresses, raw identifiers, or
the API key. Nothing here changes the network.
"""
from __future__ import annotations

import hashlib
import importlib
import ipaddress
import json
import math
import os
import re
import socket
import ssl
import time
from datetime import datetime, timezone
from http.client import HTTPException as TransportError, HTTPSConnection
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

BASE_PATH = "/proxy/network/integration/v1"
USER_AGENT = "Hermes-UniFi/0.3.0"
MAX_BYTES = 5 * 1024 * 1024
MAX_PAGES = 10
PAGE_LIMIT = 200
MAX_DEVICE_DETAILS = 60
TEXT_LIMIT = 160
PRIVATE_SUFFIXES = (".local", ".lan", ".home", ".internal", ".home.arpa")
SECRET_NAME = "UNIFI_NETWORK_API_KEY"
_retry_until = 0.0
_handles: dict[str, tuple[str, str]] = {}
_reverse: dict[tuple[str, str], str] = {}

MESSAGES = {
    "not_configured": "Configure the console host and the profile-scoped UniFi Network API key in plugin settings.",
    "invalid_console_host": "The console host must be a private LAN address or local hostname, with no scheme, path, or credentials.",
    "invalid_certificate_pin": "The console certificate pin must be a 64-character SHA-256 hex fingerprint.",
    "certificate_untrusted": "The console certificate is not trusted by this system. Confirm its SHA-256 fingerprint in the console and save it as the certificate pin.",
    "certificate_mismatch": "The console presented a certificate that does not match the configured fingerprint.",
    "authentication_failed": "The UniFi console rejected the Network API key.",
    "rate_limited": "The UniFi console rate limit was reached.",
    "upstream_http_error": "The UniFi console returned an HTTP error.",
    "console_unreachable": "The UniFi console could not be reached.",
    "invalid_upstream_response": "The UniFi console returned an invalid response.",
}
DEVICE_STATES = {"ONLINE", "OFFLINE", "PENDING_ADOPTION", "UPDATING", "GETTING_READY", "ADOPTING",
                 "DELETING", "CONNECTION_INTERRUPTED", "ISOLATED", "U5G_INCORRECT_TOPOLOGY"}
MAC_PATTERN = re.compile(r"(?<![0-9a-f])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![0-9a-f])", re.I)
IPV4_PATTERN = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
IPV6_CANDIDATE = re.compile(r"(?<![0-9a-f:.])[0-9a-f:]*:[0-9a-f:]*:[0-9a-f:.]*(?![0-9a-f:.])", re.I)
ENUM_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")


class ConsoleError(Exception):
    def __init__(self, code, status=502, retry_after=None):
        self.code, self.status, self.retry_after = code, status, retry_after
        self.message = MESSAGES[code]
        super().__init__(self.message)


class PinMismatch(Exception):
    """Deliberately not an OSError so urllib cannot swallow it into URLError."""


class Config:
    __slots__ = ("host", "pin", "show_addresses", "key")

    def __init__(self, host, pin, show_addresses, key):
        self.host, self.pin, self.show_addresses, self.key = host, pin, show_addresses, key


# --------------------------------------------------------------------------- configuration

def _plugin_settings():
    try:
        config_module = importlib.import_module("hermes_cli.config")
        config = config_module.load_config_readonly() or {}
    except Exception:
        return {}
    node = config
    for key in ("plugins", "entries", "unifi", "settings"):
        node = node.get(key) if isinstance(node, dict) else None
    return node if isinstance(node, dict) else {}


def load_secret(name=SECRET_NAME, environ=None):
    environ = os.environ if environ is None else environ
    try:
        scope = importlib.import_module("agent.secret_scope")
    except ModuleNotFoundError as exc:
        if exc.name not in {"agent", "agent.secret_scope"}:
            raise ConsoleError("not_configured", 503) from None
        value = environ.get(name)
    except Exception:
        raise ConsoleError("not_configured", 503) from None
    else:
        try:
            value = scope.get_secret(name, None)
        except Exception:
            raise ConsoleError("not_configured", 503) from None
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 33 or ord(c) > 126 for c in value):
        raise ConsoleError("not_configured", 503)
    return value


def truthy(value):
    return value is True or (isinstance(value, str) and value.strip().lower() in {"1", "true", "yes", "on"})


def validate_host(raw):
    if not isinstance(raw, str):
        raise ConsoleError("invalid_console_host", 503)
    value = raw.strip().lower()
    if not value:
        raise ConsoleError("not_configured", 503)
    if len(value) > 253 or "://" in value or any(c in value for c in "/?#@ \t\\"):
        raise ConsoleError("invalid_console_host", 503)
    if value.count(":") > 1 and not value.startswith("["):
        value = f"[{value}]"  # bare IPv6 literal
    try:
        parts = urlsplit("//" + value)
        hostname, port = parts.hostname, parts.port
    except ValueError:
        raise ConsoleError("invalid_console_host", 503) from None
    if not hostname or (port is not None and not 1 <= port <= 65535):
        raise ConsoleError("invalid_console_host", 503)
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None:
        if not (address.is_private or address.is_link_local) or address.is_loopback or address.is_multicast \
                or address.is_unspecified or address.is_reserved:
            raise ConsoleError("invalid_console_host", 503)
        literal = f"[{address.compressed}]" if address.version == 6 else address.compressed
    else:
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,62})(?:\.[a-z0-9](?:[a-z0-9-]{0,62}))*", hostname):
            raise ConsoleError("invalid_console_host", 503)
        if "." in hostname and not hostname.endswith(PRIVATE_SUFFIXES):
            raise ConsoleError("invalid_console_host", 503)
        literal = hostname
    return f"{literal}:{port}" if port else literal


def validate_pin(raw):
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    if not isinstance(raw, str):
        raise ConsoleError("invalid_certificate_pin", 503)
    value = re.sub(r"[\s:]", "", raw).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ConsoleError("invalid_certificate_pin", 503)
    return value


def load_config(settings=None, environ=None):
    settings = _plugin_settings() if settings is None else settings
    environ = os.environ if environ is None else environ
    host = validate_host(settings.get("console_host") or environ.get("UNIFI_CONSOLE_HOST") or "")
    pin = validate_pin(settings.get("console_cert_sha256") or environ.get("UNIFI_CONSOLE_CERT_SHA256") or "")
    show = truthy(settings.get("show_addresses", environ.get("UNIFI_SHOW_ADDRESSES", "")))
    key = load_secret(SECRET_NAME, environ)
    return Config(host, pin, show, key)


def configured(settings=None, environ=None):
    try:
        load_config(settings, environ)
        return True, None
    except ConsoleError as exc:
        return False, exc.code


# --------------------------------------------------------------------------- transport

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PinnedHTTPSConnection(HTTPSConnection):
    """Connect only to an address validated here, then verify the pinned certificate."""

    pin = None
    server_name = None

    def connect(self):
        if self.server_name:
            # Resolved and validated by resolve_private(); connect to that address, verify against the name.
            self.sock = socket.create_connection((self.host, self.port), self.timeout, self.source_address)
            self.sock = self._context.wrap_socket(self.sock, server_hostname=self.server_name)
        else:
            super().connect()
        der = self.sock.getpeercert(binary_form=True)
        if not der or hashlib.sha256(der).hexdigest() != self.pin:
            self.close()
            raise PinMismatch()


class PinnedHTTPSHandler(HTTPSHandler):
    """Certificate identity is the pinned fingerprint; CA and hostname checks are replaced, not skipped."""

    def __init__(self, pin, server_name=None):
        # Pinning, not disabling: UniFi consoles ship self-signed certificates that no CA can vouch for.
        # The chain/hostname checks below are replaced by PinnedHTTPSConnection.connect(), which
        # compares the peer certificate's SHA-256 to the user-confirmed fingerprint and fails closed.
        # This handler is only constructed when a pin is configured (see opener_for).
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        super().__init__(context=context)
        self.pinned_context = context
        self.pin = pin
        self.server_name = server_name

    def https_open(self, req):
        def factory(host, **kwargs):
            connection = PinnedHTTPSConnection(host, **kwargs)
            connection.pin = self.pin
            connection.server_name = self.server_name
            return connection
        return self.do_open(factory, req, context=self.pinned_context)


class HostPinnedHTTPSHandler(HTTPSHandler):
    """CA-verified TLS, but connected to an address we validated instead of one DNS returns at connect time."""

    def __init__(self, server_name):
        super().__init__(context=ssl.create_default_context())
        self.server_name = server_name

    def https_open(self, req):
        def factory(host, **kwargs):
            connection = PinnedHTTPSConnection(host, **kwargs)
            connection.pin = None
            connection.server_name = self.server_name
            return connection
        return self.do_open(factory, req, context=self._context)


def private_address(ip):
    return (ip.is_private or ip.is_link_local) and not (ip.is_loopback or ip.is_multicast or ip.is_unspecified or ip.is_reserved)


def resolve_private(config):
    """Validate the console's address and pin it for this request.

    A hostname is resolved once, every answer must be private, and the connection is then made to the
    validated address. Re-resolving at connect time would allow DNS rebinding to a public host after
    validation. Returns (connect_host, port, server_name_or_None).
    """
    parts = urlsplit("//" + config.host)
    hostname, port = parts.hostname, parts.port or 443
    if not hostname:
        raise ConsoleError("invalid_console_host", 503)
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        if not private_address(literal):
            raise ConsoleError("invalid_console_host", 503)
        return (f"[{literal.compressed}]" if literal.version == 6 else literal.compressed), port, None
    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except OSError:
        raise ConsoleError("console_unreachable", 502) from None
    addresses = {info[4][0] for info in infos if len(info) > 4 and info[4]}
    if not addresses:
        raise ConsoleError("console_unreachable", 502)
    resolved = []
    for value in addresses:
        try:
            ip = ipaddress.ip_address(value)
        except ValueError:
            raise ConsoleError("invalid_console_host", 503) from None
        if not private_address(ip):
            raise ConsoleError("invalid_console_host", 503)
        resolved.append(ip)
    chosen = sorted(resolved, key=lambda ip: (ip.version, ip.compressed))[0]
    return (f"[{chosen.compressed}]" if chosen.version == 6 else chosen.compressed), port, hostname


def retry_seconds(value):
    if not isinstance(value, str) or len(value) > 32:
        return None
    value = value.strip(" \t")
    if not re.fullmatch(r"[0-9]{1,6}(?:\.[0-9]{1,18})?", value):
        return None
    whole, _, fraction = value.partition(".")
    return min(int(whole) + int(any(digit != "0" for digit in fraction)), 86400)


def opener_for(config, server_name=None):
    if config.pin:
        handler = PinnedHTTPSHandler(config.pin, server_name)
    elif server_name:
        handler = HostPinnedHTTPSHandler(server_name)
    else:
        handler = HTTPSHandler(context=ssl.create_default_context())
    return build_opener(ProxyHandler({}), handler, NoRedirect())


def request(path, params=None, timeout=10, config=None):
    global _retry_until
    if not isinstance(path, str) or not path.startswith("/") or any(s in path for s in ("..", "?", "#", "//")):
        raise ValueError("Unsupported path")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= timeout <= 30:
        raise ValueError("Timeout must be between 1 and 30 seconds")
    config = load_config() if config is None else config
    remaining = math.ceil(_retry_until - time.monotonic())
    if remaining > 0:
        raise ConsoleError("rate_limited", 429, remaining)
    host, port, server_name = resolve_private(config)
    authority = f":{port}" if port != 443 else ""
    url = f"https://{host}{authority}{BASE_PATH}{path}"
    if params:
        url += "?" + urlencode(params)
    headers = {"X-API-KEY": config.key, "Accept": "application/json", "User-Agent": USER_AGENT}
    if server_name:
        headers["Host"] = f"{config.host.split(':', 1)[0] if ':' in config.host and config.host.count(':') == 1 else config.host}{authority}"
    req = Request(url, headers=headers, method="GET")
    try:
        with opener_for(config, server_name).open(req, timeout=timeout) as response:
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ConsoleError("invalid_upstream_response")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ConsoleError("invalid_upstream_response")
        return payload
    except PinMismatch:
        raise ConsoleError("certificate_mismatch", 502) from None
    except HTTPError as exc:
        status = exc.code
        retry = retry_seconds(exc.headers.get("Retry-After")) if exc.headers else None
        exc.close()
        if status == 429:
            retry = 60 if retry is None else retry
            _retry_until = max(_retry_until, time.monotonic() + retry)
            raise ConsoleError("rate_limited", 429, retry) from None
        if status in (401, 403):
            raise ConsoleError("authentication_failed", 401) from None
        raise ConsoleError("upstream_http_error", 502) from None
    except URLError as exc:
        if isinstance(getattr(exc, "reason", None), ssl.SSLCertVerificationError):
            raise ConsoleError("certificate_untrusted", 502) from None
        raise ConsoleError("console_unreachable", 502) from None
    except (OSError, TimeoutError, TransportError):
        raise ConsoleError("console_unreachable", 502) from None
    except (ValueError, TypeError, RecursionError):
        raise ConsoleError("invalid_upstream_response") from None


def list_all(path, config):
    """Offset pagination bounded by MAX_PAGES; returns (rows, partial)."""
    rows, offset = [], 0
    for _ in range(MAX_PAGES):
        payload = request(path, {"offset": offset, "limit": PAGE_LIMIT}, config=config)
        data = payload.get("data")
        if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
            raise ConsoleError("invalid_upstream_response")
        rows.extend(data)
        total = payload.get("totalCount")
        total = total if type(total) is int and total >= 0 else None
        if not data or len(data) < PAGE_LIMIT or (total is not None and offset + len(data) >= total):
            return rows, False
        offset += len(data)
    return rows, True


def peek_certificate(config=None, timeout=10):
    """TLS handshake only, no API key sent. Lets the user confirm a self-signed console fingerprint."""
    config = load_config() if config is None else config
    parts = urlsplit("//" + config.host)
    # Unverified handshake by design: this reads the fingerprint the user must then confirm against
    # the console UI and save as the pin. No request, header, or API key is ever sent on this socket.
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    connection = HTTPSConnection(parts.hostname or "", parts.port or 443, timeout=timeout, context=context)
    try:
        connection.connect()
        der = connection.sock.getpeercert(binary_form=True)
    except (OSError, TimeoutError, TransportError):
        raise ConsoleError("console_unreachable") from None
    finally:
        connection.close()
    if not der:
        raise ConsoleError("invalid_upstream_response")
    digest = hashlib.sha256(der).hexdigest()
    return {"sha256": digest, "matchesPin": config.pin == digest if config.pin else None}


# --------------------------------------------------------------------------- projections

def handle(kind, upstream_id):
    if not isinstance(upstream_id, str) or not upstream_id:
        return None
    key = (kind, upstream_id)
    if key not in _reverse:
        _reverse[key] = f"{kind}-{sum(1 for k in _reverse if k[0] == kind) + 1}"
        _handles[_reverse[key]] = key
    return _reverse[key]


def resolve(handle_value):
    return _handles.get(handle_value) if isinstance(handle_value, str) else None


def obj(value):
    return value if isinstance(value, dict) else {}


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def flag(value):
    return value if isinstance(value, bool) else None


def enum(value):
    return value if isinstance(value, str) and ENUM_PATTERN.fullmatch(value) else None


def stamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc).isoformat() if parsed.tzinfo else None


def clean_text(value, config):
    if not isinstance(value, str):
        return None
    if config.key and config.key in value:
        return None
    text = "".join(c for c in value if c.isprintable())[:TEXT_LIMIT]
    text = MAC_PATTERN.sub("[mac hidden]", text)
    if not config.show_addresses:
        text = IPV4_PATTERN.sub("[address hidden]", text)
        text = IPV6_CANDIDATE.sub(_hide_ipv6, text)
    return text or None


def _hide_ipv6(match):
    try:
        ipaddress.IPv6Address(match.group(0))
    except ValueError:
        return match.group(0)
    return "[address hidden]"


def address(value, config):
    if not config.show_addresses or not isinstance(value, str):
        return None
    try:
        return ipaddress.ip_address(value.strip()).compressed
    except ValueError:
        return None


def project_port(port):
    poe = obj(port.get("poe"))
    return {"idx": number(port.get("idx")), "state": enum(port.get("state")), "connector": enum(port.get("connector")),
            "speedMbps": number(port.get("speedMbps")), "maxSpeedMbps": number(port.get("maxSpeedMbps")),
            "poe": {"enabled": flag(poe.get("enabled")), "state": enum(poe.get("state")),
                    "standard": enum(poe.get("standard"))} if poe else None}


def project_radio(radio, retries_by_band):
    band = number(radio.get("frequencyGHz"))
    return {"frequencyGHz": band, "channel": number(radio.get("channel")), "channelWidthMHz": number(radio.get("channelWidthMHz")),
            "txPowerMode": enum(radio.get("txPowerMode")), "wlanStandard": enum(radio.get("wlanStandard")),
            "txRetriesPct": retries_by_band.get(band)}


def project_device(overview, details, stats, config):
    details, stats = obj(details), obj(stats)
    interfaces = obj(details.get("interfaces"))
    stat_interfaces = obj(stats.get("interfaces"))
    retries = {}
    for radio in stat_interfaces.get("radios") or []:
        radio = obj(radio)
        if number(radio.get("frequencyGHz")) is not None:
            retries[number(radio.get("frequencyGHz"))] = number(radio.get("txRetriesPct"))
    features = overview.get("features") if isinstance(overview.get("features"), list) else []
    uplink = obj(stats.get("uplink"))
    return {
        "handle": handle("device", overview.get("id")),
        "name": clean_text(overview.get("name"), config),
        "model": clean_text(overview.get("model"), config),
        "state": enum(overview.get("state")) if overview.get("state") in DEVICE_STATES else None,
        "supported": flag(overview.get("supported")),
        "firmwareVersion": clean_text(overview.get("firmwareVersion"), config),
        "firmwareUpdatable": flag(overview.get("firmwareUpdatable")),
        "ipAddress": address(overview.get("ipAddress"), config),
        "features": sorted({f for f in features if enum(f)}),
        "uplinkHandle": handle("device", obj(details.get("uplink")).get("deviceId")),
        "ports": [project_port(p) for p in interfaces.get("ports") or [] if isinstance(p, dict)],
        "radios": [project_radio(r, retries) for r in interfaces.get("radios") or [] if isinstance(r, dict)],
        "stats": {
            "cpuUtilizationPct": number(stats.get("cpuUtilizationPct")),
            "memoryUtilizationPct": number(stats.get("memoryUtilizationPct")),
            "loadAverage1Min": number(stats.get("loadAverage1Min")),
            "uptimeSec": number(stats.get("uptimeSec")),
            "lastHeartbeatAt": stamp(stats.get("lastHeartbeatAt")),
            "nextHeartbeatAt": stamp(stats.get("nextHeartbeatAt")),
            "uplinkRxRateBps": number(uplink.get("rxRateBps")),
            "uplinkTxRateBps": number(uplink.get("txRateBps")),
        } if stats else None,
    }


def project_client(row, config):
    access = obj(row.get("access"))
    return {"handle": handle("client", row.get("id")), "name": clean_text(row.get("name"), config),
            "type": enum(row.get("type")), "connectedAt": stamp(row.get("connectedAt")),
            "ipAddress": address(row.get("ipAddress"), config), "accessType": enum(access.get("type")),
            "authorized": flag(access.get("authorized")), "uplinkHandle": handle("device", row.get("uplinkDeviceId"))}


def project_network(row, config):
    return {"handle": handle("network", row.get("id")), "name": clean_text(row.get("name"), config),
            "vlanId": number(row.get("vlanId")), "enabled": flag(row.get("enabled")), "default": flag(row.get("default")),
            "management": enum(row.get("management")), "origin": enum(obj(row.get("metadata")).get("origin"))}


def project_wifi(row, config):
    return {"handle": handle("wifi", row.get("id")), "name": clean_text(row.get("name"), config),
            "enabled": flag(row.get("enabled")), "type": enum(row.get("type")),
            "security": enum(obj(row.get("securityConfiguration")).get("type")),
            "networkType": enum(obj(row.get("network")).get("type")), "origin": enum(obj(row.get("metadata")).get("origin"))}


def project_wan(row, config):
    return {"handle": handle("wan", row.get("id")), "name": clean_text(row.get("name"), config)}


FATAL = {"not_configured", "invalid_console_host", "invalid_certificate_pin", "certificate_untrusted",
         "certificate_mismatch", "authentication_failed", "rate_limited"}


def snapshot(config=None, now=None):
    """Read everything the diagnostics engine needs; tolerate per-section failures, fail closed on trust errors."""
    config = load_config() if config is None else config
    now = datetime.now(timezone.utc) if now is None else now
    errors, partial = [], False

    def section(name, fn):
        nonlocal partial
        try:
            return fn()
        except ConsoleError as exc:
            if exc.code in FATAL:
                raise
            errors.append({"section": name, "code": exc.code, "message": exc.message})
            partial = True
            return None

    info = obj(section("info", lambda: request("/info", config=config)))
    sites_rows, sites_partial = section("sites", lambda: list_all("/sites", config)) or ([], False)
    partial = partial or sites_partial
    site = next((row for row in sites_rows if isinstance(row.get("id"), str)), None)
    result = {"console": {"applicationVersion": clean_text(info.get("applicationVersion"), config),
                          "siteName": clean_text(site.get("name"), config) if site else None,
                          "siteHandle": handle("site", site.get("id")) if site else None},
              "devices": [], "clients": [], "wans": [], "networks": [], "wifi": [],
              "generatedAt": now.astimezone(timezone.utc).isoformat(), "partial": partial, "errors": errors}
    if site is None:
        result["partial"] = True
        if not any(e["section"] == "sites" for e in errors):
            errors.append({"section": "sites", "code": "invalid_upstream_response", "message": "No site was reported by the console."})
        return result
    base = f"/sites/{site['id']}"
    devices_rows, devices_partial = section("devices", lambda: list_all(base + "/devices", config)) or ([], False)
    partial = partial or devices_partial or len(devices_rows) > MAX_DEVICE_DETAILS
    for row in devices_rows[:MAX_DEVICE_DETAILS]:
        if not isinstance(row.get("id"), str):
            continue
        details = section("device-details", lambda r=row: request(f"{base}/devices/{r['id']}", config=config))
        stats = section("device-statistics", lambda r=row: request(f"{base}/devices/{r['id']}/statistics/latest", config=config))
        result["devices"].append(project_device(row, details, stats, config))
    for name, suffix, projector in (("clients", "/clients", project_client), ("wans", "/wans", project_wan),
                                    ("networks", "/networks", project_network), ("wifi", "/wifi/broadcasts", project_wifi)):
        rows, more = section(name, lambda s=suffix: list_all(base + s, config)) or ([], False)
        partial = partial or more
        result[name] = [projector(r, config) for r in rows]
    result["partial"] = partial
    return result
