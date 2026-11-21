#!/usr/bin/env python3
"""Capture only the six checked-in synthetic previews with local Chrome/Chromium."""

import argparse
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import zlib


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "screenshots"
VIEWS = ("overview", "diagnostics", "sites", "devices", "isp", "clients")
EXPECTED_SIZES = {
    "overview": (1440, 900),
    "diagnostics": (1440, 1200),
    "sites": (1440, 900),
    "devices": (1440, 900),
    "isp": (1440, 900),
    "clients": (1440, 900),
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
TEARDOWN_WATCHDOG = "Teardown watchdog expired; recording dump and terminating"


def valid_png(data: bytes, size: tuple[int, int]) -> bool:
    """Check the complete PNG container, chunk checksums and IDAT stream."""
    if not data.startswith(PNG_SIGNATURE):
        return False
    offset = len(PNG_SIGNATURE)
    seen_ihdr = seen_idat = False
    idat = []
    row_bytes = 0
    while offset + 12 <= len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        end = offset + 12 + length
        if end > len(data):
            return False
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:end - 4]
        checksum = struct.unpack_from(">I", data, end - 4)[0]
        if zlib.crc32(kind + payload) != checksum:
            return False
        if not seen_ihdr:
            if kind != b"IHDR" or length != 13 or struct.unpack_from(">II", payload) != size:
                return False
            depth, color, compression, filtering, interlace = payload[8:]
            channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color)
            allowed_depths = {0: (1, 2, 4, 8, 16), 2: (8, 16),
                              3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
            if (channels is None or depth not in allowed_depths[color]
                    or compression or filtering or interlace):
                return False
            row_bytes = (size[0] * channels * depth + 7) // 8
            seen_ihdr = True
        elif kind == b"IHDR":
            return False
        if kind == b"IDAT":
            seen_idat = True
            idat.append(payload)
        if kind == b"IEND":
            if length or end != len(data) or not seen_idat:
                return False
            try:
                stream = zlib.decompressobj()
                pixels = stream.decompress(b"".join(idat), (row_bytes + 1) * size[1] + 1)
                return (stream.eof and not stream.unused_data and not stream.unconsumed_tail
                        and len(pixels) == (row_bytes + 1) * size[1]
                        and all(pixels[row * (row_bytes + 1)] <= 4 for row in range(size[1])))
            except zlib.error:
                return False
        offset = end
    return False


def capture(chrome: Path, output_dir: Path, timeout: float) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    # Chrome never uses the caller's browser profile; all browser state is discarded.
    with (tempfile.TemporaryDirectory(prefix="unifi-chrome-") as profile,
          tempfile.TemporaryDirectory(prefix="unifi-captures-", dir=output_dir) as staging):
        for view in VIEWS:
            source = SOURCE / f"{view}.html"
            if not source.is_file():
                raise RuntimeError(f"Missing synthetic HTML preview: {source}")
            size = EXPECTED_SIZES[view]
            png = Path(staging) / f"{view}.png"
            command = [
                str(chrome),
                "--headless",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-networking",
                "--disable-extensions",
                "--disable-sync",
                "--disable-component-update",
                "--host-resolver-rules=MAP * ~NOTFOUND",
                f"--user-data-dir={profile}",
                f"--window-size={size[0]},{size[1]}",
                f"--screenshot={png}",
                source.resolve().as_uri(),
            ]
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(f"Chrome timed out after {timeout:g}s capturing {view}") from exc
            except OSError as exc:
                raise RuntimeError(f"Could not launch Chrome for {view}: {exc}") from exc
            teardown_only = result.returncode == 2 and TEARDOWN_WATCHDOG in result.stderr
            if result.returncode and not teardown_only:
                raise RuntimeError(
                    f"Chrome failed capturing {view} (exit {result.returncode}): "
                    f"{result.stderr.strip() or result.stdout.strip() or 'no error output'}"
                )
            try:
                image = png.read_bytes()
            except OSError as exc:
                raise RuntimeError(f"Chrome did not produce {view}.png: {exc}") from exc
            if not valid_png(image, size):
                raise RuntimeError(f"Invalid {view}.png: expected a {size[0]}x{size[1]} PNG")
            if teardown_only:
                print(f"Warning: Chrome teardown watchdog expired after capturing {view}.png "
                      f"(exit 2); validated complete PNG", file=sys.stderr)
        # No destination is replaced until all six staged PNGs pass validation.
        for view in VIEWS:
            size = EXPECTED_SIZES[view]
            (Path(staging) / f"{view}.png").replace(output_dir / f"{view}.png")
            print(f"Captured {view}.png ({size[0]}x{size[1]})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", required=True, type=Path, help="path to a Chrome/Chromium executable")
    parser.add_argument("--output-dir", type=Path, default=SOURCE, help="PNG destination (default: docs/screenshots)")
    parser.add_argument("--timeout", type=float, default=30, help="seconds per view (default: 30)")
    args = parser.parse_args()
    chrome = args.chrome.expanduser().resolve()
    if not chrome.is_file() or not os.access(chrome, os.X_OK):
        parser.error(f"Chrome/Chromium executable not found or not executable: {chrome}")
    if not 0 < args.timeout < float("inf"):
        parser.error("--timeout must be a finite positive number")
    try:
        capture(chrome, args.output_dir.expanduser().resolve(), args.timeout)
    except (OSError, RuntimeError) as exc:
        print(f"Screenshot capture failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
