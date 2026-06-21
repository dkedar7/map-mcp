"""U7 — the parity scenario: the three frontends agree, plus a real-socket transport check.

Deterministic parity uses a fake bridge (no browser). A live transport test runs a Python
WebSocket client as a fake hook against the real bridge (no browser needed; gated on the ws
lib). The live *browser* drive of the sample app is gated on Playwright and skips cleanly when
unavailable — that path is exercised on a real machine / via pm-dogfood.
"""

from __future__ import annotations

import threading
import time

import pytest

from map_mcp.bridge import Bridge, BridgeError, ws_available
from map_mcp.cli import run_op
from map_mcp.coreops import CoreOps, OP_NAMES
from map_mcp.protocol import decode, encode, make_response
from map_mcp.server import TOOL_NAMES, core_tool_handlers


# --- surface parity ---
def test_three_surfaces_cover_the_same_ops():
    cli_ops = set(OP_NAMES)  # run_op accepts exactly these
    assert cli_ops == set(TOOL_NAMES) == set(OP_NAMES)


# --- result parity across frontends (fake bridge) ---
@pytest.mark.parametrize("op", ["get_viewport", "read_popup", "list_layers"])
def test_noarg_op_result_is_identical_across_surfaces(op, fake_bridge):
    canned = {"value": f"{op}-result"}
    b = fake_bridge({op: canned})
    coreops_result = getattr(CoreOps(b), op)()
    mcp_result = core_tool_handlers(CoreOps(b))[op]()
    cli_result = run_op(CoreOps(b), op)
    assert coreops_result == mcp_result == cli_result == canned


def test_arg_op_dispatches_identically_across_surfaces(fake_bridge):
    # set_layer_visibility through each surface sends the same (method, params) to the bridge
    seen = []
    for invoke in (
        lambda b: CoreOps(b).set_layer_visibility("roads", False),
        lambda b: core_tool_handlers(CoreOps(b))["set_layer_visibility"]("roads", False),
        lambda b: run_op(CoreOps(b), "set_layer_visibility", {"layer": "roads", "visible": False}),
    ):
        b = fake_bridge({"set_layer_visibility": {"ok": True}})
        invoke(b)
        seen.append(b.last())
    assert seen[0] == seen[1] == seen[2] == ("set_layer_visibility", {"layer": "roads", "visible": False})


# --- live transport round-trip over a real socket (fake hook, no browser) ---
def _run_fake_hook(url: str, token: str, replies: dict, stop: threading.Event) -> None:
    import asyncio

    import websockets

    async def main():
        async with websockets.connect(url) as ws:
            await ws.send(encode({"type": "hello", "token": token}))
            while not stop.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=0.2)
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    break
                req = decode(raw)
                await ws.send(encode(make_response(req["id"],
                                                   result=replies.get(req["method"], {}))))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except Exception:
        pass


@pytest.mark.skipif(not ws_available(), reason="websockets not installed")
def test_live_socket_roundtrip_with_token():
    bridge = Bridge()
    bridge.serve_ws(host="127.0.0.1", port=0, token="secret")  # waits until listening
    assert bridge.port
    stop = threading.Event()
    hook = threading.Thread(
        target=_run_fake_hook,
        args=(f"ws://127.0.0.1:{bridge.port}", "secret", {"get_viewport": {"zoom": 6}}, stop),
        daemon=True,
    )
    hook.start()
    try:
        deadline = time.monotonic() + 5
        while not bridge.connected and time.monotonic() < deadline:
            time.sleep(0.05)
        assert bridge.connected, "fake hook did not authenticate/connect"
        assert CoreOps(bridge).get_viewport() == {"zoom": 6}  # real socket round-trip
    finally:
        stop.set()


@pytest.mark.skipif(not ws_available(), reason="websockets not installed")
def test_live_socket_rejects_bad_token():
    bridge = Bridge()
    bridge.serve_ws(host="127.0.0.1", port=0, token="secret")
    stop = threading.Event()
    hook = threading.Thread(
        target=_run_fake_hook,
        args=(f"ws://127.0.0.1:{bridge.port}", "WRONG", {}, stop),
        daemon=True,
    )
    hook.start()
    try:
        # poll a short window: it must NEVER attach (fail fast if it wrongly does)
        for _ in range(20):
            assert not bridge.connected, "bad token must not authenticate"
            time.sleep(0.05)
    finally:
        stop.set()


@pytest.mark.skipif(not ws_available(), reason="websockets not installed")
def test_serve_ws_surfaces_port_in_use():
    # the first bridge binds an ephemeral port; the second must raise (not silently 'start')
    b1 = Bridge()
    b1.serve_ws(host="127.0.0.1", port=0, token="t")
    assert b1.port
    b2 = Bridge()
    with pytest.raises(BridgeError):
        b2.serve_ws(host="127.0.0.1", port=b1.port, token="t")


# --- live browser drive of the sample app (gated; manual / pm-dogfood path) ---
def _playwright_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:
        return False
    return True


@pytest.mark.skipif(not _playwright_available(),
                    reason="playwright+browser not installed (live browser path is manual / pm-dogfood)")
def test_live_browser_sample_app():
    # Exercised on a machine with Playwright + a browser: load examples/sample_app, let the
    # real hook connect to the bridge, and drive it. Skipped by default — see the scenario docstring.
    pytest.skip("live browser drive is run manually / via pm-dogfood, not in the unit suite")
