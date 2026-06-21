"""The local WebSocket bridge between this process and the in-browser map hook.

``call(method, params)`` sends a request to the connected hook and blocks until the matching
reply arrives (correlated by id). The correlation logic is synchronous and unit-testable
without a socket — feed replies via ``_on_message``. The live WebSocket server is gated on the
``websockets`` library, binds loopback only, and (with U6) requires a per-session token.

Sync-over-async: the ws server runs in a daemon thread with its own event loop; ``call`` (on
the MCP/CLI thread) waits on a threading event the receive coroutine sets. This keeps core-ops
and the MCP tools synchronous, matching streamlit-mcp's engine.
"""

from __future__ import annotations

import secrets
import threading
from typing import Any, Callable, Optional

from .protocol import decode, encode, make_request


class BridgeError(RuntimeError):
    """Raised when no map is connected, a call times out, or the hook returns an error."""


def ws_available() -> bool:
    try:
        import websockets  # noqa: F401
    except Exception:
        return False
    return True


def authenticate(first_message: str, expected_token: Optional[str]) -> bool:
    """Validate the hook's opening ``{type:"hello", token}`` frame against the session token.

    Pure (no I/O), so the handshake rule is unit-testable. When no token is configured
    (``expected_token`` falsy) the gate is open — but the CLI always issues a token."""
    if not expected_token:
        return True
    try:
        msg = decode(first_message)
    except Exception:
        return False
    if msg.get("type") != "hello":
        return False
    # constant-time compare so token validation leaks no timing signal
    return secrets.compare_digest(str(msg.get("token") or ""), str(expected_token))


class _Pending:
    __slots__ = ("event", "result", "error")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.result: Any = None
        self.error: Optional[str] = None


class Bridge:
    """Correlates outbound requests with inbound replies by id. Transport-agnostic."""

    def __init__(self) -> None:
        self._pending: dict[Any, _Pending] = {}
        self._lock = threading.Lock()
        self._sender: Optional[Callable[[str], None]] = None
        self._thread: Optional[threading.Thread] = None
        self.port: Optional[int] = None
        self._loop: Any = None

    @property
    def connected(self) -> bool:
        return self._sender is not None

    def attach_sender(self, sender: Callable[[str], None]) -> None:
        """Bind the function that writes a frame to the connected hook (last writer wins —
        a reconnect/new tab replaces the old; the old's in-flight calls then time out)."""
        self._sender = sender

    def detach(self, sender: Optional[Callable[[str], None]] = None) -> None:
        """Clear the sender on disconnect. Identity-guarded: a stale connection's teardown
        only clears the sender if it is still the *current* one — so a page reload (new
        socket attaches, then the old socket's close fires) can't null the live sender.
        Draining lets in-flight calls fail fast with 'map disconnected' instead of timing out."""
        if sender is None or self._sender is sender:
            self._sender = None
            self._drain_pending("map disconnected")

    def _drain_pending(self, message: str) -> None:
        with self._lock:
            waiting = list(self._pending.values())
        for pend in waiting:
            if pend.error is None and pend.result is None:
                pend.error = message
                pend.event.set()

    def call(self, method: str, params: Optional[dict] = None, *, timeout: float = 10.0) -> Any:
        """Send a request and block for its reply. Raises BridgeError on no-connection,
        send failure, timeout, disconnect, or an error reply — never leaks another exception."""
        sender = self._sender
        if sender is None:
            raise BridgeError("no map connected — open a hooked map and try again")
        req = make_request(method, params)
        pend = _Pending()
        with self._lock:
            self._pending[req["id"]] = pend
        try:
            try:
                sender(encode(req))
            except Exception as e:  # closed loop / dropped socket -> clean BridgeError, not a leak
                raise BridgeError(f"send failed: {e}") from e
            if not pend.event.wait(timeout):
                raise BridgeError(f"timeout after {timeout}s waiting for {method!r}")
            if pend.error is not None:
                raise BridgeError(pend.error)
            return pend.result
        finally:
            with self._lock:
                self._pending.pop(req["id"], None)

    def _on_message(self, text: str) -> None:
        """Resolve the pending call matching this reply's id. Unknown/stale ids are ignored."""
        try:
            msg = decode(text)
        except Exception:
            return
        with self._lock:
            pend = self._pending.get(msg.get("id"))
        if pend is None:
            return
        if msg.get("ok"):
            pend.result = msg.get("result")
        else:
            pend.error = msg.get("error") or "unknown error from hook"
        pend.event.set()

    # ------------------------------------------------------------- live server
    def serve_ws(self, host: str = "127.0.0.1", port: int = 8765,
                 token: Optional[str] = None) -> None:
        """Start the loopback WebSocket server in a daemon thread (non-blocking).

        Gated on ``websockets``. Binds loopback only. The token handshake is layered in U6;
        v1 here wires connect -> sender, and routes inbound frames to ``_on_message``.
        """
        if not ws_available():
            raise BridgeError("websockets not installed — `pip install map-mcp` includes it")
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise BridgeError(f"refusing to bind non-loopback host {host!r} (local-only)")

        import asyncio

        import websockets

        loop = asyncio.new_event_loop()
        self._loop = loop
        ready = threading.Event()
        startup: dict[str, BaseException] = {}

        async def handler(ws):
            # Token handshake (local-only security): require a valid hello before accepting
            # commands, so a stray page on the loopback port can't drive the operator's map.
            if token:
                try:
                    first = await asyncio.wait_for(ws.recv(), timeout=10)
                except Exception:
                    return
                if not authenticate(first, token):
                    await ws.close(code=4001, reason="bad token")
                    return
            send = lambda text: asyncio.run_coroutine_threadsafe(ws.send(text), loop)
            self.attach_sender(send)
            try:
                async for message in ws:
                    self._on_message(message)
            finally:
                self.detach(send)  # identity-guarded: only clears if still the current sender

        async def main():
            async with websockets.serve(handler, host, port) as server:
                try:
                    self.port = server.sockets[0].getsockname()[1]
                except Exception:
                    self.port = port
                ready.set()
                await asyncio.Future()  # serve forever

        def run():
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(main())
            except BaseException as e:  # bind failure (port in use), etc.
                startup["error"] = e
                ready.set()  # unblock the waiter so it can surface the error

        self._thread = threading.Thread(target=run, daemon=True, name="map-mcp-bridge")
        self._thread.start()
        # Don't return until the server is actually listening — and surface startup failure
        # (a port-in-use bind error would otherwise die silently in the thread).
        if not ready.wait(timeout=5):
            raise BridgeError("bridge did not start within 5s")
        if "error" in startup:
            raise BridgeError(f"bridge failed to start: {startup['error']}")
