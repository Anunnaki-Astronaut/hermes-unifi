"""Agent tool schemas: what the model sees. Every tool is read-only and takes no URL, path,
credential, identifier, or free-form command; the only inputs are a short search word and a focus area."""

QUERY = {"type": "string",
         "description": "Optional short search text (up to 80 characters) matched against names and models. Case-insensitive."}

STATUS = {
    "name": "unifi_status",
    "description": (
        "Read-only one-paragraph health summary of the user's UniFi network: how many devices and clients, whether anything "
        "is down, and the headline of the latest diagnostics. Use this first when the user asks how the network is doing. "
        "It never changes anything on the network."),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

DIAGNOSE = {
    "name": "unifi_diagnose",
    "description": (
        "Read-only diagnostics of the user's UniFi network in plain English: offline devices, firmware, CPU/memory, Wi-Fi "
        "retries and channel conflicts, slow or PoE-limited ports, open Wi-Fi, internet packet loss/downtime, stranded clients. "
        "Each finding has a severity, an explanation, and a recommendation. Suggested fixes are described but never executed; "
        "the user applies changes in the UniFi console. Use when the user reports a problem or asks for recommendations."),
    "parameters": {
        "type": "object",
        "properties": {
            "focus": {"type": "string",
                      "enum": ["all", "devices", "wifi", "wired", "internet", "clients", "security", "firmware", "resources", "stability"],
                      "description": "Limit findings to one area. Default all."},
        },
        "required": [],
    },
}

DEVICES = {
    "name": "unifi_devices",
    "description": (
        "Read-only list of UniFi devices (gateway, switches, access points) with state, model, firmware, uptime, CPU/memory, "
        "radio channels and port link speeds. Identifiers are opaque handles like device-2; MAC addresses are never returned "
        "and IP addresses only when the user enabled that in plugin settings."),
    "parameters": {"type": "object", "properties": {"query": QUERY}, "required": []},
}

CLIENTS = {
    "name": "unifi_clients",
    "description": (
        "Read-only list of clients currently connected to the user's UniFi network: name, wired/wireless, which device they "
        "connect through, guest authorization, connection time. MAC addresses are never returned; IP addresses only when the "
        "user enabled that in plugin settings. Use to answer 'is my X connected' or 'what is on the network'."),
    "parameters": {"type": "object", "properties": {"query": QUERY}, "required": []},
}

ALL = {schema["name"]: schema for schema in (STATUS, DIAGNOSE, DEVICES, CLIENTS)}
