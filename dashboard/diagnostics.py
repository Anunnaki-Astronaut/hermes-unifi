"""Deterministic, read-only diagnostics over a projected console snapshot.

Every rule yields plain-English findings with a recommendation. Nothing here
contacts the network or changes anything; ``fix`` entries describe an action a
future write phase could offer and are marked unavailable in this version.
"""
from __future__ import annotations

from datetime import datetime, timezone

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2, "ok": 3}
STATE_WORDS = {
    "ONLINE": "online", "OFFLINE": "offline", "PENDING_ADOPTION": "waiting to be adopted",
    "UPDATING": "updating its firmware", "GETTING_READY": "getting ready", "ADOPTING": "being adopted",
    "DELETING": "being removed", "CONNECTION_INTERRUPTED": "losing its connection to the console",
    "ISOLATED": "isolated (it cannot reach its uplink)", "U5G_INCORRECT_TOPOLOGY": "wired in an unsupported topology",
}
DOWN_STATES = {"OFFLINE", "CONNECTION_INTERRUPTED", "ISOLATED"}
TRANSITION_STATES = {"UPDATING", "GETTING_READY", "ADOPTING", "PENDING_ADOPTION", "DELETING"}
WRITES_UNAVAILABLE = "Write actions are not enabled in this version; apply the change in the UniFi console."
BAND_LABEL = {0.9: "900 MHz", 2.4: "2.4 GHz", 5: "5 GHz", 6: "6 GHz", 60: "60 GHz"}
CANONICAL_2G_CHANNELS = {1, 6, 11}


def label(item):
    return item.get("name") or item.get("model") or item.get("handle") or "an unnamed device"


def band(value):
    return BAND_LABEL.get(value, f"{value} GHz" if value is not None else "unknown band")


def finding(rule, severity, category, title, detail, recommendation, subject=None, evidence=None, fix=None):
    return {"id": f"{rule}:{subject['handle'] if subject and subject.get('handle') else 'site'}",
            "severity": severity, "category": category, "title": title, "detail": detail,
            "recommendation": recommendation,
            "subject": {"handle": subject.get("handle"), "name": label(subject)} if subject else None,
            "evidence": evidence or {}, "fix": fix}


def proposed(action, subject, **arguments):
    return {"action": action, "target": subject.get("handle"), "arguments": arguments,
            "available": False, "requiresApproval": True, "reason": WRITES_UNAVAILABLE}


def minutes(seconds):
    return f"{int(seconds // 60)} minute{'s' if seconds // 60 != 1 else ''}"


# --------------------------------------------------------------------------- device rules

def device_rules(devices, now):
    for device in devices:
        state = device.get("state")
        if state in DOWN_STATES:
            yield finding("device-down", "critical", "devices", f"{label(device)} is {STATE_WORDS[state]}",
                          f"The console reports {label(device)} ({device.get('model') or 'unknown model'}) as {STATE_WORDS[state]}. "
                          "Everything connected through it is affected.",
                          "Check its power or PoE source and the uplink cable first. If it has power and link lights, "
                          "restart it from the console. If it stays down, try a different switch port or cable.",
                          device, {"state": state}, proposed("RESTART_DEVICE", device))
        elif state in TRANSITION_STATES:
            yield finding("device-transition", "info", "devices", f"{label(device)} is {STATE_WORDS[state]}",
                          f"{label(device)} is temporarily {STATE_WORDS[state]}. Brief client disruption is normal.",
                          "Wait a few minutes and refresh before taking action.", device, {"state": state})
        elif state == "U5G_INCORRECT_TOPOLOGY":
            yield finding("device-topology", "warning", "devices", f"{label(device)} is {STATE_WORDS[state]}",
                          "The console flags this device's wiring as an unsupported topology.",
                          "Review how the device is cabled to its parent and follow the console's topology guidance.",
                          device, {"state": state})
        elif state is None:
            yield finding("device-state-unknown", "info", "devices", f"{label(device)} reported no state",
                          "The console did not report a recognizable state for this device.",
                          "Refresh. If it persists, check the device in the console directly.", device)
        if device.get("supported") is False:
            yield finding("device-unsupported", "warning", "devices", f"{label(device)} is not fully supported",
                          "The console marks this device as unsupported by the current Network application version.",
                          "Update the console's Network application, or expect limited management for this device.", device)
        if device.get("firmwareUpdatable") is True:
            yield finding("firmware-available", "warning", "firmware", f"Firmware update available for {label(device)}",
                          f"{label(device)} is running {device.get('firmwareVersion') or 'an unreported version'} and a newer firmware is available.",
                          "Schedule the update during a quiet period; the device will reboot and drop clients briefly.",
                          device, {"firmwareVersion": device.get("firmwareVersion")})
        stats = device.get("stats") or {}
        cpu, memory = stats.get("cpuUtilizationPct"), stats.get("memoryUtilizationPct")
        if cpu is not None and cpu >= 90:
            yield finding("cpu-high", "critical", "resources", f"{label(device)} CPU is at {cpu:.0f}%",
                          "Sustained CPU this high causes dropped packets and slow roaming.",
                          "Check for a firmware update, reduce enabled features (deep inspection, IDS/IPS) if this is the gateway, or restart the device.",
                          device, {"cpuUtilizationPct": cpu}, proposed("RESTART_DEVICE", device))
        elif cpu is not None and cpu >= 75:
            yield finding("cpu-elevated", "warning", "resources", f"{label(device)} CPU is elevated at {cpu:.0f}%",
                          "The device is busy. Occasional peaks are fine; persistent load is not.",
                          "Watch whether it stays above 75%. If so, review enabled features or firmware.", device, {"cpuUtilizationPct": cpu})
        if memory is not None and memory >= 90:
            yield finding("memory-high", "warning", "resources", f"{label(device)} memory is at {memory:.0f}%",
                          "Memory pressure on UniFi devices usually ends in a spontaneous reboot.",
                          "Restart the device during a quiet period and check for a firmware update.",
                          device, {"memoryUtilizationPct": memory}, proposed("RESTART_DEVICE", device))
        uptime = stats.get("uptimeSec")
        if uptime is not None and uptime < 900:
            yield finding("recent-restart", "info", "stability", f"{label(device)} restarted {minutes(uptime)} ago",
                          "A recent restart can explain a brief outage. Repeated restarts point to power or firmware problems.",
                          "If this repeats, check PoE budget and power cabling, then firmware.", device, {"uptimeSec": uptime})
        next_beat = stats.get("nextHeartbeatAt")
        if next_beat and state == "ONLINE":
            try:
                due = datetime.fromisoformat(next_beat)
            except ValueError:
                due = None
            if due and now - due > timedelta_seconds(120):
                yield finding("heartbeat-late", "warning", "stability", f"{label(device)} missed its last check-in",
                              "The device is marked online but has not reported to the console on time.",
                              "Refresh in a minute. If it stays late, treat it as a connectivity problem on its uplink.",
                              device, {"nextHeartbeatAt": next_beat})
        for radio in device.get("radios") or []:
            retries = radio.get("txRetriesPct")
            band_name = band(radio.get("frequencyGHz"))
            if retries is not None and retries >= 50:
                yield finding("radio-retries", "critical", "wifi", f"Very high Wi-Fi retry rate on {label(device)} ({band_name})",
                              f"About {retries:.0f}% of transmissions on the {band_name} radio are being retried. Clients will see slow, choppy Wi-Fi.",
                              "Look for interference: change the channel, narrow the channel width, or lower transmit power. "
                              "On 2.4 GHz, 20 MHz on channel 1, 6, or 11 is the safe baseline.", device,
                              {"frequencyGHz": radio.get("frequencyGHz"), "txRetriesPct": retries})
            elif retries is not None and retries >= 25:
                yield finding("radio-retries", "warning", "wifi", f"High Wi-Fi retry rate on {label(device)} ({band_name})",
                              f"About {retries:.0f}% of transmissions on the {band_name} radio are retried, which usually means interference or a distant client.",
                              "Check for neighboring networks on the same channel and consider a different channel or narrower width.",
                              device, {"frequencyGHz": radio.get("frequencyGHz"), "txRetriesPct": retries})
            if radio.get("frequencyGHz") == 2.4 and (radio.get("channelWidthMHz") or 0) > 20:
                yield finding("width-2g", "info", "wifi", f"{label(device)} uses {radio['channelWidthMHz']:.0f} MHz on 2.4 GHz",
                              "Wide channels on 2.4 GHz overlap neighbors and rarely improve speed for the devices that use that band.",
                              "Set the 2.4 GHz channel width to 20 MHz.", device, {"channelWidthMHz": radio.get("channelWidthMHz")})
            if radio.get("frequencyGHz") == 2.4 and radio.get("channel") not in (None, *CANONICAL_2G_CHANNELS):
                yield finding("channel-2g", "info", "wifi", f"{label(device)} is on 2.4 GHz channel {radio['channel']:.0f}",
                              "Channels other than 1, 6, and 11 partially overlap two neighbors at once.",
                              "Use channel 1, 6, or 11 on 2.4 GHz.", device, {"channel": radio.get("channel")})
        for port in device.get("ports") or []:
            speed, maximum = port.get("speedMbps"), port.get("maxSpeedMbps")
            if port.get("state") == "UP" and speed is not None and maximum and speed <= 100 < maximum:
                yield finding("port-slow", "warning", "wired", f"Port {port.get('idx')} on {label(device)} linked at {speed:.0f} Mbps",
                              f"This port can do {maximum:.0f} Mbps but negotiated only {speed:.0f} Mbps, which usually means a damaged cable, a bad connector, or an old device at the other end.",
                              "Reseat or replace the cable. If the connected device is gigabit-capable, test it on another port.",
                              device, {"portIdx": port.get("idx"), "speedMbps": speed, "maxSpeedMbps": maximum})
            poe = port.get("poe") or {}
            if poe.get("state") == "LIMITED":
                yield finding("poe-limited", "warning", "wired", f"PoE is limited on port {port.get('idx')} of {label(device)}",
                              "The switch is not delivering full power on this port, often because the PoE budget is exhausted.",
                              "Check the switch's total PoE budget and move high-draw devices to a different switch or injector.",
                              device, {"portIdx": port.get("idx")}, proposed("POWER_CYCLE_PORT", device, portIdx=port.get("idx")))


def timedelta_seconds(seconds):
    from datetime import timedelta
    return timedelta(seconds=seconds)


# --------------------------------------------------------------------------- site rules

def channel_overlap_rules(devices):
    groups = {}
    for device in devices:
        if device.get("state") not in ("ONLINE", None):
            continue
        for radio in device.get("radios") or []:
            key = (radio.get("frequencyGHz"), radio.get("channel"))
            if None not in key:
                groups.setdefault(key, []).append(device)
    for (frequency, channel), members in sorted(groups.items(), key=lambda item: (item[0][0], item[0][1])):
        if len(members) > 1:
            names = ", ".join(label(d) for d in members)
            yield finding("channel-overlap", "warning", "wifi", f"{len(members)} access points share {band(frequency)} channel {channel:.0f}",
                          f"{names} are all broadcasting on the same channel and compete for airtime.",
                          "Let the console auto-select channels, or assign different non-overlapping channels to nearby access points.",
                          None, {"frequencyGHz": frequency, "channel": channel, "devices": [d.get("handle") for d in members]})


def wifi_rules(wifi):
    for network in wifi:
        if network.get("enabled") is False:
            yield finding("wifi-disabled", "info", "wifi", f"Wi-Fi network {label(network)} is disabled",
                          "This SSID exists but is not broadcasting.", "Enable it if devices are expected to use it; otherwise remove it to keep the configuration tidy.",
                          network)
            continue
        if network.get("security") == "OPEN":
            yield finding("wifi-open", "warning", "security", f"Wi-Fi network {label(network)} has no encryption",
                          "Anyone in range can join and see unencrypted traffic.",
                          "Use WPA2/WPA3 Personal, or if this is a guest network, make sure guest isolation is on.", network,
                          {"security": "OPEN"})
        elif network.get("security") == "WPA2_PERSONAL":
            yield finding("wifi-wpa2-only", "info", "security", f"Wi-Fi network {label(network)} uses WPA2 only",
                          "WPA2 is still acceptable, but newer devices support WPA3.",
                          "Consider WPA2/WPA3 mixed mode once you confirm older devices still connect.", network,
                          {"security": "WPA2_PERSONAL"})


def wan_rules(wans, cloud_isp, require_wan=True):
    if not wans and require_wan:
        yield finding("wan-missing", "warning", "internet", "No WAN interface reported",
                      "The console did not list an internet (WAN) interface for this site.",
                      "If this console is the gateway, check its WAN port and ISP link. If another router handles the internet, this is expected.")
    for row in cloud_isp or []:
        name = row.get("ispName") or row.get("label") or "the internet connection"
        if (row.get("packetLoss") or 0) > 0:
            yield finding("isp-packet-loss", "warning", "internet", f"Packet loss on {name}",
                          f"The latest ISP period reported packet loss of {row['packetLoss']}.",
                          "Power-cycle the modem/ONT if loss persists, then contact the ISP with the time and numbers.",
                          None, {"packetLoss": row.get("packetLoss"), "metricTime": row.get("metricTime")})
        if (row.get("downtime") or 0) > 0:
            yield finding("isp-downtime", "warning", "internet", f"Internet downtime on {name}",
                          f"The latest ISP period reported downtime of {row['downtime']}.",
                          "Check the modem/ONT status lights and the gateway WAN port; repeated downtime is an ISP ticket.",
                          None, {"downtime": row.get("downtime"), "metricTime": row.get("metricTime")})
        if (row.get("avgLatency") or 0) > 100:
            yield finding("isp-latency", "warning", "internet", f"High latency on {name}",
                          f"Average latency in the latest period was {row['avgLatency']}.",
                          "Look for a saturated upload (large backups or uploads) and enable Smart Queues if the link is small.",
                          None, {"avgLatency": row.get("avgLatency")})


def client_rules(clients, devices):
    if not clients:
        return
    wired = sum(1 for c in clients if c.get("type") == "WIRED")
    wireless = sum(1 for c in clients if c.get("type") == "WIRELESS")
    other = len(clients) - wired - wireless
    summary = f"{wired} wired, {wireless} wireless" + (f", {other} VPN or other" if other else "")
    yield finding("clients-summary", "ok", "clients", f"{len(clients)} client{'s' if len(clients) != 1 else ''} connected",
                  f"Currently connected: {summary}.", "No action needed.", None, {"wired": wired, "wireless": wireless, "other": other})
    unauthorized = [c for c in clients if c.get("authorized") is False]
    if unauthorized:
        yield finding("clients-unauthorized", "info", "clients", f"{len(unauthorized)} guest client{'s' if len(unauthorized) != 1 else ''} waiting for authorization",
                      "Guests on a captive-portal network cannot reach the internet until authorized.",
                      "Authorize them from the console if they are expected guests.", None, {"count": len(unauthorized)})
    down = {d.get("handle") for d in devices if d.get("state") in DOWN_STATES}
    stranded = [c for c in clients if c.get("uplinkHandle") in down]
    if stranded:
        yield finding("clients-stranded", "warning", "clients", f"{len(stranded)} client{'s' if len(stranded) != 1 else ''} last seen on a device that is down",
                      "These clients were connected through a device the console now reports as down.",
                      "Fix the down device first; the clients will reconnect on their own.", None, {"count": len(stranded)})


def coverage_rules(snapshot):
    if snapshot.get("partial") or snapshot.get("errors"):
        sections = sorted({e.get("section") for e in snapshot.get("errors") or [] if e.get("section")})
        detail = "Some console data could not be read" + (f" ({', '.join(sections)})" if sections else "") + \
                 ". Findings below are based on what was available."
        yield finding("coverage-partial", "info", "coverage", "Diagnostics are based on partial data", detail,
                      "Refresh. If a section keeps failing, check the console's Network API key permissions.",
                      None, {"sections": sections})


def missing_console_rules():
    yield finding("console-not-connected", "info", "coverage", "Local console is not connected",
                  "Only Site Manager cloud data was checked, so devices, clients, Wi-Fi, ports, and internet health "
                  "were not examined. Site Manager itself exposes no device or client inventory to this plugin.",
                  "In Settings → Plugins → UniFi, set the console host and the Network API key to enable local diagnostics.",
                  None, {})


# --------------------------------------------------------------------------- report

def analyze(snapshot, cloud_isp=None, now=None, console_configured=True):
    now = datetime.now(timezone.utc) if now is None else now
    devices = snapshot.get("devices") or []
    if console_configured:
        findings = list(device_rules(devices, now))
        findings += list(channel_overlap_rules(devices))
        findings += list(wifi_rules(snapshot.get("wifi") or []))
        findings += list(wan_rules(snapshot.get("wans") or [], cloud_isp))
        findings += list(client_rules(snapshot.get("clients") or [], devices))
        findings += list(coverage_rules(snapshot))
    else:
        findings = list(missing_console_rules()) + list(wan_rules([], cloud_isp, require_wan=False))
    if not any(f["severity"] in ("critical", "warning") for f in findings) and console_configured:
        findings.append(finding("all-clear", "ok", "summary", "No problems detected",
                                f"{len(devices)} device{'s' if len(devices) != 1 else ''} checked; nothing needs attention right now.",
                                "No action needed."))
    findings.sort(key=lambda f: (SEVERITY_ORDER[f["severity"]], f["title"]))
    counts = {level: sum(1 for f in findings if f["severity"] == level) for level in SEVERITY_ORDER}
    return {"generatedAt": now.astimezone(timezone.utc).isoformat(), "console": snapshot.get("console") or {},
            "summary": counts, "headline": headline(counts), "findings": findings,
            "readOnly": True, "deviceCount": len(devices), "clientCount": len(snapshot.get("clients") or []),
            "consoleConnected": console_configured}


def headline(counts):
    parts = []
    if counts.get("critical"):
        parts.append(f"{counts['critical']} critical problem{'s' if counts['critical'] != 1 else ''}")
    if counts.get("warning"):
        parts.append(f"{counts['warning']} warning{'s' if counts['warning'] != 1 else ''}")
    if counts.get("info"):
        parts.append(f"{counts['info']} note{'s' if counts['info'] != 1 else ''}")
    return ", ".join(parts) if parts else "Network looks healthy"


def plain_text(report):
    lines = [f"UniFi network check — {report['headline']}."]
    for level, heading in (("critical", "Critical"), ("warning", "Warnings"), ("info", "Notes"), ("ok", "OK")):
        items = [f for f in report["findings"] if f["severity"] == level]
        if not items:
            continue
        lines.append("")
        lines.append(f"{heading}:")
        for f in items:
            lines.append(f"- {f['title']}. {f['detail']}")
            if f["recommendation"] and f["recommendation"] != "No action needed.":
                lines.append(f"  What to do: {f['recommendation']}")
    return "\n".join(lines)
