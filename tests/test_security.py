"""U6 tests — the token handshake (pure) and the loopback-only bind guard."""

from __future__ import annotations

import pytest

from map_mcp.bridge import Bridge, BridgeError, authenticate
from map_mcp.protocol import encode


def test_authenticate_accepts_matching_hello():
    assert authenticate(encode({"type": "hello", "token": "abc"}), "abc") is True


def test_authenticate_rejects_wrong_token():
    assert authenticate(encode({"type": "hello", "token": "nope"}), "abc") is False


def test_authenticate_rejects_missing_token_or_type():
    assert authenticate(encode({"type": "hello"}), "abc") is False
    assert authenticate(encode({"token": "abc"}), "abc") is False


def test_authenticate_rejects_malformed_frame():
    assert authenticate("not json", "abc") is False


def test_authenticate_open_gate_when_no_token():
    # documented: no configured token -> open (but the CLI always sets one)
    assert authenticate("anything", None) is True
    assert authenticate("anything", "") is True


def test_serve_ws_refuses_non_loopback():
    with pytest.raises(BridgeError):
        Bridge().serve_ws(host="0.0.0.0", port=8765, token="t")
