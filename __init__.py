"""Hermes discovers the dashboard API and Desktop entry declaratively; this registers the read-only agent tools."""
import importlib.util
import sys
from pathlib import Path

TOOLSET = "unifi"
EMOJI = "📡"


def _load(stem):
    name = f"hermes_unifi_root_{stem}"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(f"{stem}.py"))
    if spec is None or spec.loader is None:
        raise ImportError(stem)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def register(ctx):
    """Four read-only tools. No hooks, no writes, no network contact at registration time."""
    schemas, tools = _load("schemas"), _load("tools")
    for name, schema in schemas.ALL.items():
        ctx.register_tool(name=name, toolset=TOOLSET, schema=schema, handler=tools.HANDLERS[name], emoji=EMOJI)
