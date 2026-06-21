"""U3 tests — core-ops sends the right method+params and returns the hook's result (fake bridge)."""

from __future__ import annotations

import pytest

from map_mcp.bridge import BridgeError
from map_mcp.coreops import CoreOps, _bbox, _point


def test_get_viewport_passes_through(fake_bridge):
    b = fake_bridge({"get_viewport": {"zoom": 4, "center": [0, 0]}})
    assert CoreOps(b).get_viewport() == {"zoom": 4, "center": [0, 0]}
    assert b.last() == ("get_viewport", {})


def test_query_rendered_features_point_vs_bbox_vs_neither(fake_bridge):
    b = fake_bridge({"query_rendered_features": {"features": []}})
    co = CoreOps(b)
    co.query_rendered_features(point=[12.5, 41.9])
    assert b.last() == ("query_rendered_features", {"point": [12.5, 41.9]})
    co.query_rendered_features(bbox=[[0, 0], [1, 1]], layers=["roads"], limit=50)
    assert b.last() == ("query_rendered_features",
                        {"bbox": [[0.0, 0.0], [1.0, 1.0]], "layers": ["roads"], "limit": 50})
    co.query_rendered_features()
    assert b.last() == ("query_rendered_features", {})  # whole viewport


def test_click_at_sends_point(fake_bridge):
    b = fake_bridge({"click_at": {"features": [], "popup": ["hi"]}})
    out = CoreOps(b).click_at([12.5, 41.9])
    assert out["popup"] == ["hi"]
    assert b.last() == ("click_at", {"point": [12.5, 41.9]})


def test_set_layer_visibility_roundtrips_bool(fake_bridge):
    b = fake_bridge({"set_layer_visibility": {"layer": "roads", "visibility": "none"}})
    co = CoreOps(b)
    co.set_layer_visibility("roads", False)
    assert b.last() == ("set_layer_visibility", {"layer": "roads", "visible": False})
    co.set_layer_visibility("roads", True)
    assert b.last() == ("set_layer_visibility", {"layer": "roads", "visible": True})


def test_set_view_requires_something(fake_bridge):
    with pytest.raises(ValueError):
        CoreOps(fake_bridge()).set_view()


def test_set_view_builds_params(fake_bridge):
    b = fake_bridge({"set_view": {"zoom": 8}})
    CoreOps(b).set_view(center=[10, 20], zoom=8)
    assert b.last() == ("set_view", {"center": [10.0, 20.0], "zoom": 8.0})


def test_bridge_error_propagates_cleanly(fake_bridge):
    b = fake_bridge({"get_viewport": BridgeError("no map connected")})
    with pytest.raises(BridgeError):
        CoreOps(b).get_viewport()


def test_set_layer_visibility_requires_layer(fake_bridge):
    with pytest.raises(ValueError):
        CoreOps(fake_bridge()).set_layer_visibility("", True)


def test_point_and_bbox_validation():
    with pytest.raises(ValueError):
        _point([1, 2, 3])
    with pytest.raises(ValueError):
        _bbox([[1, 2]])
    assert _point((1, 2)) == [1.0, 2.0]
