"""Fail-closed checks for Chrome screenshot capture."""
import importlib.util
from pathlib import Path
import struct
import subprocess
import sys
import zlib

import pytest

from conftest import ROOT


spec = importlib.util.spec_from_file_location(
    "capture_screenshots_under_test", ROOT / "scripts" / "capture_screenshots.py"
)
capture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = capture
spec.loader.exec_module(capture)

WATCHDOG = "Teardown watchdog expired; recording dump and terminating"


def chunk(kind, data):
    return (struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data)))


def png_bytes(width=1440, height=900):
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    scanlines = (b"\0" + b"\0" * (width * 3)) * height
    return (capture.PNG_SIGNATURE + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(scanlines))
            + chunk(b"IEND", b""))


def png_with_idat(raw):
    ihdr = struct.pack(">IIBBBBB", 1440, 900, 8, 2, 0, 0, 0)
    return (capture.PNG_SIGNATURE + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


@pytest.mark.parametrize(
    "returncode,stderr,image,accepted",
    [
        (0, "", png_bytes(), True),
        (2, WATCHDOG, png_bytes(), True),
        (2, "unrelated failure", png_bytes(), False),
        (1, WATCHDOG, png_bytes(), False),
        (2, WATCHDOG, None, False),
        (2, WATCHDOG, png_bytes()[:-4], False),
        (2, WATCHDOG, png_bytes() + b"trailing", False),
        (2, WATCHDOG, png_bytes()[:-12] + chunk(b"IEND", b"extra"), False),
        (2, WATCHDOG, png_bytes()[:-12] + chunk(b"IEND", b"")[:-1] + b"\0", False),
        (2, WATCHDOG, capture.PNG_SIGNATURE + chunk(
            b"IHDR", struct.pack(">IIBBBBB", 1440, 899, 8, 2, 0, 0, 0)
        ) + png_bytes()[33:], False),
        (2, WATCHDOG, png_with_idat(b"\0"), False),
        (0, "", png_bytes()[:-4], False),
    ],
)
def test_capture_exit_and_png_validation(monkeypatch, tmp_path, capsys,
                                         returncode, stderr, image, accepted):
    monkeypatch.setattr(capture, "VIEWS", ("overview",))
    destination = tmp_path / "overview.png"
    destination.write_bytes(b"previous capture")

    def run(command, **kwargs):
        if image is not None:
            Path(next(arg.split("=", 1)[1] for arg in command
                      if arg.startswith("--screenshot="))).write_bytes(image)
        return subprocess.CompletedProcess(command, returncode, "", stderr)

    monkeypatch.setattr(capture.subprocess, "run", run)
    if accepted:
        capture.capture(Path("/fake/chrome"), tmp_path, 30)
        assert destination.read_bytes() == image
        assert ("Warning:" in capsys.readouterr().err) == (returncode == 2)
    else:
        with pytest.raises(RuntimeError):
            capture.capture(Path("/fake/chrome"), tmp_path, 30)
        assert destination.read_bytes() == b"previous capture"


@pytest.mark.parametrize("height,accepted", [(1200, True), (900, False), (1199, False)])
def test_diagnostics_requires_tall_png(monkeypatch, tmp_path, height, accepted):
    monkeypatch.setattr(capture, "VIEWS", ("diagnostics",))
    image = png_bytes(height=height)
    destination = tmp_path / "diagnostics.png"
    destination.write_bytes(b"previous capture")

    def run(command, **kwargs):
        assert "--window-size=1440,1200" in command
        Path(next(arg.split("=", 1)[1] for arg in command
                  if arg.startswith("--screenshot="))).write_bytes(image)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(capture.subprocess, "run", run)
    if accepted:
        capture.capture(Path("/fake/chrome"), tmp_path, 30)
        assert destination.read_bytes() == image
    else:
        with pytest.raises(RuntimeError, match="1440x1200"):
            capture.capture(Path("/fake/chrome"), tmp_path, 30)
        assert destination.read_bytes() == b"previous capture"


def test_late_invalid_view_preserves_all_existing_pngs(monkeypatch, tmp_path):
    previous = {}
    for view in capture.VIEWS:
        previous[view] = f"previous {view}".encode()
        (tmp_path / f"{view}.png").write_bytes(previous[view])
    calls = []

    def run(command, **kwargs):
        view = Path(command[-1]).stem
        calls.append(view)
        image = png_bytes(height=1200 if view == "diagnostics" else
                          899 if view == "clients" else 900)
        Path(next(arg.split("=", 1)[1] for arg in command
                  if arg.startswith("--screenshot="))).write_bytes(image)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(capture.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="Invalid clients.png"):
        capture.capture(Path("/fake/chrome"), tmp_path, 30)
    assert calls == list(capture.VIEWS)
    for view, old in previous.items():
        assert (tmp_path / f"{view}.png").read_bytes() == old
