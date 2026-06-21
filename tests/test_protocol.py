"""U1 tests — the pure protocol and the bridge's id-correlation (no real socket)."""

from __future__ import annotations

import threading

import pytest

from map_mcp.bridge import Bridge, BridgeError, ws_available
from map_mcp.protocol import decode, encode, make_request, make_response


# --- protocol (pure) ---
def test_request_response_roundtrip():
    req = make_request("get_viewport", {"x": 1}, id=7)
    assert decode(encode(req)) == {"id": 7, "method": "get_viewport", "params": {"x": 1}}
    ok = make_response(7, result={"zoom": 4})
    assert decode(encode(ok)) == {"id": 7, "ok": True, "result": {"zoom": 4}}
    err = make_response(7, error="boom")
    assert decode(encode(err)) == {"id": 7, "ok": False, "error": "boom"}


def test_make_request_requires_method():
    with pytest.raises(ValueError):
        make_request("")


def test_decode_rejects_non_object():
    with pytest.raises(ValueError):
        decode("[1, 2, 3]")


def test_ids_are_monotonic():
    a = make_request("m")["id"]
    b = make_request("m")["id"]
    assert b > a


# --- bridge correlation (no real ws) ---
def _reply_async(bridge, mid, *, result=None, error=None, delay=0.0):
    """Feed a reply into the bridge as if the hook sent it, on a timer."""
    def fire():
        bridge._on_message(encode(make_response(mid, result=result, error=error)))
    t = threading.Timer(delay, fire)
    t.start()
    return t


def test_call_resolves_on_matching_reply():
    bridge = Bridge()
    sent = {}
    bridge.attach_sender(lambda text: sent.update(decode(text)))  # capture the outbound id
    # reply on a short timer with the id the bridge assigned
    def sender(text):
        msg = decode(text)
        _reply_async(bridge, msg["id"], result={"zoom": 5}, delay=0.01)
    bridge.attach_sender(sender)
    assert bridge.call("get_viewport", timeout=2) == {"zoom": 5}


def test_call_without_connection_raises():
    bridge = Bridge()  # no sender attached
    with pytest.raises(BridgeError):
        bridge.call("get_viewport")


def test_call_times_out_cleanly():
    bridge = Bridge()
    bridge.attach_sender(lambda text: None)  # never replies
    with pytest.raises(BridgeError):
        bridge.call("get_viewport", timeout=0.05)


def test_error_reply_surfaces_as_bridge_error():
    bridge = Bridge()
    def sender(text):
        _reply_async(bridge, decode(text)["id"], error="layer not found", delay=0.01)
    bridge.attach_sender(sender)
    with pytest.raises(BridgeError) as e:
        bridge.call("set_layer_visibility", {"layer": "x"}, timeout=2)
    assert "layer not found" in str(e.value)


def test_stale_id_is_ignored():
    bridge = Bridge()
    # a reply for an unknown id must not crash and must not resolve anything
    bridge._on_message(encode(make_response(999, result="nope")))
    bridge.attach_sender(lambda text: None)
    with pytest.raises(BridgeError):
        bridge.call("get_viewport", timeout=0.05)  # still times out (stale reply ignored)


def test_ws_available_is_bool():
    assert isinstance(ws_available(), bool)
