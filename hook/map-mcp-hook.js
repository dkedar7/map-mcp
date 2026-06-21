/*
 * map-mcp hook (stub — U1 transport spike).
 *
 * Connects out to the local map-mcp bridge and echoes a `ping` as `pong` so the round-trip
 * can be proven before the real MapLibre operations land (U2). Vanilla JS, no build step.
 *
 *   mapMcp.connect({ url: "ws://127.0.0.1:8765", token: "..." })
 */
(function (global) {
  "use strict";

  function connect(opts) {
    opts = opts || {};
    var url = opts.url || "ws://127.0.0.1:8765";
    var ws = new WebSocket(url);

    ws.onmessage = function (ev) {
      var req;
      try { req = JSON.parse(ev.data); } catch (e) { return; }
      var reply = { id: req.id, ok: true, result: null };
      try {
        if (req.method === "ping") {
          reply.result = "pong";
        } else {
          reply.ok = false;
          reply.error = "unknown method: " + req.method + " (hook stub — U2 adds real ops)";
        }
      } catch (e) {
        reply.ok = false;
        reply.error = String(e);
      }
      ws.send(JSON.stringify(reply));
    };

    return ws;
  }

  global.mapMcp = { connect: connect };
})(typeof window !== "undefined" ? window : this);
