"""Core operations — the single implementation each frontend (MCP server + CLI) calls.

Every op issues one bridge call and returns the hook's structured result. The bridge is
injected, so a fake bridge makes this layer fully unit-testable without a browser. Input
validation lives here (geographic inputs are ``[lng, lat]``); the hook does the MapLibre work.
A bridge error (no map connected, timeout, hook error) propagates as ``BridgeError`` — the
frontends turn it into a clean tool/CLI error.
"""

from __future__ import annotations

from typing import Any, Optional

# The canonical operation surface. The MCP tool set and the CLI command set both cover exactly
# these — the parity contract (asserted in the scenario test).
OP_NAMES = (
    "get_viewport",
    "query_rendered_features",
    "get_features_at",
    "click_at",
    "read_popup",
    "set_view",
    "list_layers",
    "set_layer_visibility",
    "screenshot",
)


class CoreOps:
    def __init__(self, bridge: Any) -> None:
        self.bridge = bridge

    def get_viewport(self) -> dict:
        return self.bridge.call("get_viewport")

    def query_rendered_features(
        self,
        point: Optional[list] = None,
        bbox: Optional[list] = None,
        layers: Optional[list] = None,
        limit: Optional[int] = None,
    ) -> dict:
        params: dict = {}
        if point is not None:
            params["point"] = _point(point)
        if bbox is not None:
            params["bbox"] = _bbox(bbox)
        if layers:
            params["layers"] = list(layers)
        if limit is not None:
            params["limit"] = int(limit)
        return self.bridge.call("query_rendered_features", params)

    def get_features_at(self, point: list, layers: Optional[list] = None) -> dict:
        params: dict = {"point": _point(point)}
        if layers:
            params["layers"] = list(layers)
        return self.bridge.call("get_features_at", params)

    def click_at(self, point: list, layers: Optional[list] = None) -> dict:
        params: dict = {"point": _point(point)}
        if layers:
            params["layers"] = list(layers)
        return self.bridge.call("click_at", params)

    def read_popup(self) -> dict:
        return self.bridge.call("read_popup")

    def set_view(
        self,
        center: Optional[list] = None,
        zoom: Optional[float] = None,
        bbox: Optional[list] = None,
        bearing: Optional[float] = None,
        pitch: Optional[float] = None,
    ) -> dict:
        params: dict = {}
        if center is not None:
            params["center"] = _point(center)
        if zoom is not None:
            params["zoom"] = float(zoom)
        if bbox is not None:
            params["bbox"] = _bbox(bbox)
        if bearing is not None:
            params["bearing"] = float(bearing)
        if pitch is not None:
            params["pitch"] = float(pitch)
        if not params:
            raise ValueError("set_view needs at least one of center/zoom/bbox/bearing/pitch")
        return self.bridge.call("set_view", params)

    def list_layers(self) -> dict:
        return self.bridge.call("list_layers")

    def set_layer_visibility(self, layer: str, visible: bool) -> dict:
        if not layer:
            raise ValueError("set_layer_visibility needs a layer id")
        return self.bridge.call("set_layer_visibility",
                                {"layer": layer, "visible": bool(visible)})

    def screenshot(self) -> dict:
        return self.bridge.call("screenshot")


def _point(p: Any) -> list:
    if not (isinstance(p, (list, tuple)) and len(p) == 2):
        raise ValueError(f"point must be [lng, lat], got {p!r}")
    return [float(p[0]), float(p[1])]


def _bbox(b: Any) -> list:
    if not (isinstance(b, (list, tuple)) and len(b) == 2):
        raise ValueError(f"bbox must be [[lng,lat],[lng,lat]], got {b!r}")
    return [_point(b[0]), _point(b[1])]
