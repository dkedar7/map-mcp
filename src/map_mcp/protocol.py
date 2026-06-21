"""Pure wire protocol for the bridge: request/response envelopes + id correlation.

No I/O — fully unit-testable. Both the live socket (``bridge.py``) and the in-browser hook
speak this. A request is ``{id, method, params}``; a reply is ``{id, ok, result}`` on success
or ``{id, ok=false, error}`` on failure.
"""

from __future__ import annotations

import itertools
import json
from typing import Any, Optional

_counter = itertools.count(1)


def next_id() -> int:
    """Monotonic request id (process-local)."""
    return next(_counter)


def make_request(method: str, params: Optional[dict] = None, *, id: Optional[int] = None) -> dict:
    if not method:
        raise ValueError("request needs a method")
    return {
        "id": id if id is not None else next_id(),
        "method": method,
        "params": params or {},
    }


def make_response(id: Any, *, result: Any = None, error: Optional[str] = None) -> dict:
    if error is not None:
        return {"id": id, "ok": False, "error": error}
    return {"id": id, "ok": True, "result": result}


def encode(msg: dict) -> str:
    return json.dumps(msg)


def decode(text: str) -> dict:
    msg = json.loads(text)
    if not isinstance(msg, dict):
        raise ValueError("envelope must be a JSON object")
    return msg
