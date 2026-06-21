"""FastMCP server: exposes the core operations as MCP tools over stdio and HTTP/SSE.

Tool bodies are thin — they call the shared ``CoreOps`` (the same layer the CLI uses, so parity
holds). A no-map-connected / hook error / bad input is failed closed into a clean ``{"error":
...}`` result rather than a raised exception, so an agent gets a message it can act on. HTTP/SSE
refuses non-loopback binds (the bridge is local-only).
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from fastmcp import FastMCP

from .bridge import BridgeError
from .coreops import OP_NAMES, CoreOps

TOOL_NAMES = OP_NAMES
VALID_TRANSPORTS = ("stdio", "http", "sse")


def _guard(fn: Callable) -> Callable:
    """Fail closed: turn a no-connection/hook/input error into a clean error result.

    Matches the CLI's run_op catch set (BridgeError, ValueError, TypeError) so the two
    frontends fail closed identically. The bridge converts transport faults (closed loop,
    dropped socket) into BridgeError at the source, so nothing else should escape here."""
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (BridgeError, ValueError, TypeError) as e:
            return {"error": str(e)}
    return wrapped


def core_tool_handlers(ops: CoreOps) -> dict[str, Callable]:
    """The tool implementations bound to one CoreOps — directly unit-testable."""
    return {
        "get_viewport": _guard(lambda: ops.get_viewport()),
        "query_rendered_features": _guard(
            lambda point=None, bbox=None, layers=None, limit=None:
            ops.query_rendered_features(point, bbox, layers, limit)),
        "get_features_at": _guard(lambda point, layers=None: ops.get_features_at(point, layers)),
        "click_at": _guard(lambda point, layers=None: ops.click_at(point, layers)),
        "read_popup": _guard(lambda: ops.read_popup()),
        "set_view": _guard(lambda center=None, zoom=None, bbox=None, bearing=None, pitch=None:
                           ops.set_view(center, zoom, bbox, bearing, pitch)),
        "list_layers": _guard(lambda: ops.list_layers()),
        "set_layer_visibility": _guard(lambda layer, visible: ops.set_layer_visibility(layer, visible)),
        "screenshot": _guard(lambda: ops.screenshot()),
    }


def build_server(bridge: Any, app_name: str = "map-mcp"):
    """Construct a FastMCP server exposing the core tools, bound to one bridge."""
    mcp = FastMCP(app_name)
    H = core_tool_handlers(CoreOps(bridge))

    @mcp.tool
    def get_viewport() -> dict:
        """Current viewport: center [lng,lat], zoom, bearing, pitch, bounds."""
        return H["get_viewport"]()

    @mcp.tool
    def query_rendered_features(point: Optional[list] = None, bbox: Optional[list] = None,
                                layers: Optional[list] = None, limit: Optional[int] = None) -> dict:
        """Features currently rendered, optionally at a [lng,lat] point or within a [[lng,lat],[lng,lat]] bbox."""
        return H["query_rendered_features"](point=point, bbox=bbox, layers=layers, limit=limit)

    @mcp.tool
    def get_features_at(point: list, layers: Optional[list] = None) -> dict:
        """Features rendered at a [lng,lat] point."""
        return H["get_features_at"](point, layers)

    @mcp.tool
    def click_at(point: list, layers: Optional[list] = None) -> dict:
        """Fire the map's click at a [lng,lat] point (runs app popup handlers) and return features + popup."""
        return H["click_at"](point, layers)

    @mcp.tool
    def read_popup() -> dict:
        """Text of any open map popup(s)."""
        return H["read_popup"]()

    @mcp.tool
    def set_view(center: Optional[list] = None, zoom: Optional[float] = None,
                 bbox: Optional[list] = None, bearing: Optional[float] = None,
                 pitch: Optional[float] = None) -> dict:
        """Move the map: center+zoom (and bearing/pitch), or fit a bbox. Returns the new viewport."""
        return H["set_view"](center=center, zoom=zoom, bbox=bbox, bearing=bearing, pitch=pitch)

    @mcp.tool
    def list_layers() -> dict:
        """The style's layers with id, type, source, and visibility."""
        return H["list_layers"]()

    @mcp.tool
    def set_layer_visibility(layer: str, visible: bool) -> dict:
        """Show or hide a layer by id."""
        return H["set_layer_visibility"](layer, visible)

    @mcp.tool
    def screenshot() -> dict:
        """A PNG data URL of the current map (needs preserveDrawingBuffer:true on the map)."""
        return H["screenshot"]()

    return mcp


def validate_transport(transport: str) -> str:
    if transport not in VALID_TRANSPORTS:
        raise ValueError(f"transport must be one of {VALID_TRANSPORTS}, got {transport!r}")
    return transport


def run_server(bridge: Any, transport: str = "stdio", host: str = "127.0.0.1",
               port: int = 8000) -> None:
    """Build and run the MCP server (blocking). The bridge's ws server is started separately."""
    validate_transport(transport)
    if transport in ("http", "sse") and host not in ("127.0.0.1", "::1", "localhost"):
        raise ValueError(
            f"Refusing to serve {transport} on non-loopback host {host!r}: the map bridge is "
            "local-only. Bind 127.0.0.1, or use stdio."
        )
    mcp = build_server(bridge)
    if transport == "stdio":
        mcp.run()
    else:
        mcp.run(transport=transport, host=host, port=port)
