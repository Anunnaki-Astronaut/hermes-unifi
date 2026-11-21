"""Synthetic, no-network pagination and trust-boundary tests."""
import io
import json
import ssl
import types
from urllib.parse import quote

import pytest
from conftest import client as c


def envelope(rows, token=None):
    return json.dumps({"httpStatusCode": 200, "traceId": "synthetic", "data": rows,
                       "nextToken": token}).encode()


def queued(monkeypatch, pages):
    calls = []
    responses = iter(pages)
    monkeypatch.setattr(c, "load_key", lambda: "ephemeral-sentinel")
    monkeypatch.setattr(c, "_retry_until", 0.0)

    def build(*handlers):
        assert handlers[0].proxies == {}
        assert handlers[1]._context.verify_mode == ssl.CERT_REQUIRED
        assert handlers[1]._context.check_hostname
        assert isinstance(handlers[2], c.NoRedirect)

        def open(req, timeout):
            assert req.method == "GET" and req.data is None and timeout == 10
            assert req.get_header("X-api-key") == "ephemeral-sentinel"
            assert "ephemeral-sentinel" not in req.full_url
            calls.append(req.full_url)
            return io.BytesIO(next(responses))

        return types.SimpleNamespace(open=open)

    monkeypatch.setattr(c, "build_opener", build)
    return calls


@pytest.mark.parametrize("view", ["sites", "devices"])
def test_follows_opaque_server_cursor_without_changing_origin(monkeypatch, view):
    token = "opaque+cursor/with &="
    calls = queued(monkeypatch, [envelope([{"page": 1}], token),
                               envelope([{"page": 2}])])
    rows, partial, key = c.request_data(view)
    assert rows == [{"page": 1}, {"page": 2}]
    assert partial is False and key == "ephemeral-sentinel"
    assert calls == [f"https://api.ui.com/v1/{view}",
                     f"https://api.ui.com/v1/{view}?nextToken={quote(token, safe='')}"]


def test_page_cap_returns_honest_partial_results(monkeypatch):
    monkeypatch.setattr(c, "MAX_PAGES", 2)
    calls = queued(monkeypatch, [envelope([{"page": 1}], "one"),
                               envelope([{"page": 2}], "two")])
    rows, partial, _ = c.request_data("sites")
    assert rows == [{"page": 1}, {"page": 2}]
    assert partial is True and len(calls) == 2


def test_byte_cap_never_parses_a_truncated_page(monkeypatch):
    first = envelope([{"page": 1}], "one")
    monkeypatch.setattr(c, "MAX_TOTAL_BYTES", len(first) + 20)
    calls = queued(monkeypatch, [first, envelope([{"page": 2}], "two")])
    rows, partial, _ = c.request_data("sites")
    assert rows == [{"page": 1}]
    assert partial is True and len(calls) == 2


@pytest.mark.parametrize("token", [7, "x" * 1025, "line\nbreak"])
def test_rejects_malformed_cursor_without_second_request(monkeypatch, token):
    calls = queued(monkeypatch, [envelope([{}], token)])
    with pytest.raises(c.SafeError) as error:
        c.request_data("devices")
    assert error.value.code == "invalid_upstream_response"
    assert len(calls) == 1


def test_repeated_cursor_fails_closed(monkeypatch):
    calls = queued(monkeypatch, [envelope([{}], "repeat"), envelope([{}], "repeat")])
    with pytest.raises(c.SafeError) as error:
        c.request_data("sites")
    assert error.value.code == "invalid_upstream_response"
    assert len(calls) == 2


def test_isp_never_uses_paginated_cursor(monkeypatch):
    calls = queued(monkeypatch, [envelope([{}], "stray")])
    rows, partial, _ = c.request_data("isp")
    assert rows == [{}] and partial is False and len(calls) == 1
