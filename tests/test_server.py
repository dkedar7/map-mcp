"""U4 tests — MCP tool handlers delegate to core-ops, fail closed, and transports validate."""

from __future__ import annotations

import pytest

from map_mcp.bridge import Bridge, BridgeError
from map_mcp.coreops import CoreOps, OP_NAMES
from map_mcp.server import build_server, core_tool_handlers, run_server, validate_transport


def test_handlers_cover_exactly_the_op_surface(fake_bridge):
    H = core_tool_handlers(CoreOps(fake_bridge()))
    assert set(H) == set(OP_NAMES)


def test_handlers_delegate_to_coreops(fake_bridge):
    b = fake_bridge({
        "get_viewport": {"zoom": 3},
        "set_layer_visibility": {"layer": "x", "visibility": "none"},
        "query_rendered_features": {"features": [{"layer": "roads"}]},
    })
    H = core_tool_handlers(CoreOps(b))
    assert H["get_viewport"]() == {"zoom": 3}
    assert H["set_layer_visibility"]("x", False) == {"layer": "x", "visibility": "none"}
    H["query_rendered_features"](point=[1, 2])
    assert b.last() == ("query_rendered_features", {"point": [1.0, 2.0]})


def test_no_map_connected_fails_closed(fake_bridge):
    b = fake_bridge({"get_viewport": BridgeError("no map connected")})
    H = core_tool_handlers(CoreOps(b))
    out = H["get_viewport"]()
    assert "error" in out and "no map connected" in out["error"]  # clean result, not a raise


def test_bad_input_fails_closed(fake_bridge):
    H = core_tool_handlers(CoreOps(fake_bridge()))
    out = H["set_layer_visibility"]("", True)  # ValueError inside -> guarded
    assert "error" in out


def test_build_server_registers_tools(fake_bridge):
    # building must not raise and must produce a FastMCP server object
    mcp = build_server(fake_bridge())
    assert mcp is not None


def test_transport_validation():
    assert validate_transport("stdio") == "stdio"
    with pytest.raises(ValueError):
        validate_transport("carrier-pigeon")


def test_http_refuses_non_loopback():
    with pytest.raises(ValueError):
        run_server(Bridge(), transport="http", host="0.0.0.0")
