"""U5 tests — run_op dispatches through core-ops (parity seam), fail-closed; parser builds."""

from __future__ import annotations

import pytest

from map_mcp.bridge import BridgeError
from map_mcp.cli import build_parser, main, run_op
from map_mcp.coreops import CoreOps, OP_NAMES
from map_mcp.server import TOOL_NAMES


def test_run_op_delegates(fake_bridge):
    b = fake_bridge({"get_viewport": {"zoom": 9}})
    assert run_op(CoreOps(b), "get_viewport") == {"zoom": 9}


def test_run_op_passes_params(fake_bridge):
    b = fake_bridge({"set_layer_visibility": {"layer": "roads", "visibility": "none"}})
    run_op(CoreOps(b), "set_layer_visibility", {"layer": "roads", "visible": False})
    assert b.last() == ("set_layer_visibility", {"layer": "roads", "visible": False})


def test_run_op_unknown_operation():
    out = run_op(CoreOps(None), "fly_to_moon")
    assert "error" in out and "unknown operation" in out["error"]


def test_run_op_no_map_fails_closed(fake_bridge):
    b = fake_bridge({"get_viewport": BridgeError("no map connected")})
    out = run_op(CoreOps(b), "get_viewport")
    assert "error" in out and "no map connected" in out["error"]


def test_run_op_bad_params_fails_closed(fake_bridge):
    out = run_op(CoreOps(fake_bridge()), "set_layer_visibility", {"nope": 1})  # TypeError
    assert "error" in out


def test_cli_command_surface_matches_mcp_tool_surface():
    # parity by construction: the CLI's operation set == the MCP tool set == OP_NAMES
    assert set(OP_NAMES) == set(TOOL_NAMES)


def test_parser_builds_and_call_validates_op():
    parser = build_parser()
    args = parser.parse_args(["call", "get_viewport"])
    assert args.op == "get_viewport"


def test_parser_constrains_transport():
    # an invalid transport is rejected at parse time (argparse choices), no socket started
    with pytest.raises(SystemExit):
        build_parser().parse_args(["serve", "--transport", "telepathy"])
