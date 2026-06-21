"""Shared test fixtures — a fake bridge so core-ops/server/CLI test without a browser."""

from __future__ import annotations

from typing import Any, Optional

import pytest


class _FakeBridge:
    """Stands in for the live WebSocket bridge. Records calls; returns canned replies.

    ``replies`` maps a method name to a result dict, or to an Exception to raise (to simulate
    a hook error / no-connection)."""

    def __init__(self, replies: Optional[dict] = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.replies = replies or {}

    def call(self, method: str, params: Optional[dict] = None, *, timeout: float = 10.0) -> Any:
        self.calls.append((method, params or {}))
        reply = self.replies.get(method, {})
        if isinstance(reply, Exception):
            raise reply
        return reply

    def last(self) -> tuple[str, dict]:
        return self.calls[-1]


@pytest.fixture
def fake_bridge():
    """Factory: ``fake_bridge({"get_viewport": {...}})`` -> a _FakeBridge."""
    def _make(replies: Optional[dict] = None) -> _FakeBridge:
        return _FakeBridge(replies)
    return _make
