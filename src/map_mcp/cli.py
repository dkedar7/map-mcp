"""map-mcp CLI — the human-first surface.

`serve` starts the bridge + the MCP server (for agents) and prints the opt-in snippet + token.
`call` / `repl` let a human drive the live map from the terminal. All paths go through the same
``CoreOps`` an agent uses over MCP, so parity holds by construction — ``run_op`` accepts exactly
the operations the MCP tools expose.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
from typing import Any, Optional

from .bridge import Bridge, BridgeError
from .coreops import OP_NAMES, CoreOps


def _force_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def run_op(ops: CoreOps, op: str, params: Optional[dict] = None) -> dict:
    """Dispatch one operation by name through core-ops. Fail-closed, like the MCP tools.

    This is the parity seam: it accepts exactly ``OP_NAMES`` — the same surface the agent has."""
    if op not in OP_NAMES:
        return {"error": f"unknown operation {op!r}; expected one of {list(OP_NAMES)}"}
    try:
        result = getattr(ops, op)(**(params or {}))
    except (BridgeError, ValueError, TypeError) as e:
        return {"error": str(e)}
    return result if isinstance(result, dict) else {"result": result}


def _snippet(ws_port: int, token: str) -> str:
    url = f"ws://127.0.0.1:{ws_port}"
    return (
        "Add this to your MapLibre page (the map is your existing maplibregl.Map):\n"
        '  <script src="map-mcp-hook.js"></script>\n'
        "  <script>\n"
        f'    mapMcp.register(map, {{ url: "{url}", token: "{token}" }});\n'
        "  </script>\n"
        f"  bridge: {url}   token: {token}"
    )


# --------------------------------------------------------------------- commands
def cmd_serve(args: argparse.Namespace) -> int:
    from .server import run_server, validate_transport
    try:
        validate_transport(args.transport)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    token = secrets.token_urlsafe(16)
    bridge = Bridge()
    try:
        bridge.serve_ws(host="127.0.0.1", port=args.ws_port, token=token)
    except Exception as e:
        print(f"could not start the map bridge: {e}", file=sys.stderr)
        return 1
    print(_snippet(args.ws_port, token), file=sys.stderr)
    try:
        run_server(bridge, transport=args.transport, host=args.host, port=args.port)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


def _wait_for_map(bridge: Bridge, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if bridge.connected:
            return True
        time.sleep(0.1)
    return bridge.connected


def cmd_call(args: argparse.Namespace) -> int:
    try:
        params = json.loads(args.params) if args.params else {}
    except json.JSONDecodeError as e:
        print(f"bad --params JSON: {e}", file=sys.stderr)
        return 1
    token = secrets.token_urlsafe(16)
    bridge = Bridge()
    try:
        bridge.serve_ws(host="127.0.0.1", port=args.ws_port, token=token)
    except Exception as e:
        print(f"could not start the map bridge: {e}", file=sys.stderr)
        return 1
    print(_snippet(args.ws_port, token), file=sys.stderr)
    if not _wait_for_map(bridge, args.wait):
        print("no map connected — open your hooked map, then retry", file=sys.stderr)
        return 1
    result = run_op(CoreOps(bridge), args.op, params)
    print(json.dumps(result, indent=2, default=str))
    return 1 if "error" in result else 0


# --------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="map-mcp",
        description="Drive and perceive an existing live MapLibre GL map (agent via MCP, or here).")
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="serve the live map over MCP (for agents)")
    p_serve.add_argument("--transport", choices=["stdio", "http", "sse"], default="stdio")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000, help="MCP HTTP/SSE port")
    p_serve.add_argument("--ws-port", dest="ws_port", type=int, default=8765,
                         help="bridge WebSocket port the hook connects to")
    p_serve.set_defaults(func=cmd_serve)

    p_call = sub.add_parser("call", help="run one operation against the live map (same ops agents use)")
    p_call.add_argument("op", choices=list(OP_NAMES))
    p_call.add_argument("--params", help="JSON params, e.g. '{\"point\":[12.5,41.9]}'")
    p_call.add_argument("--ws-port", dest="ws_port", type=int, default=8765)
    p_call.add_argument("--wait", type=float, default=30.0,
                        help="seconds to wait for the hooked map to connect")
    p_call.set_defaults(func=cmd_call)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    _force_utf8_output()
    args = build_parser().parse_args(argv)
    return args.func(args)


def _cli() -> None:
    """Console-script entry point — propagate the exit code."""
    raise SystemExit(main())


if __name__ == "__main__":
    _cli()
