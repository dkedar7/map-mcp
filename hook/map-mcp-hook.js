/*
 * map-mcp hook — expose a live MapLibre GL map to the local map-mcp bridge.
 *
 * Add this file to your page and register your map:
 *
 *   <script src="map-mcp-hook.js"></script>
 *   <script>
 *     mapMcp.register(map, { url: "ws://127.0.0.1:8765", token: "PASTE_TOKEN" });
 *   </script>
 *
 * The hook connects out to the bridge, presents the token (see snippet.md), and answers
 * requests by calling the map's own JS API. Vanilla JS, no build step. Drives an EXISTING
 * map — it never creates one. An unknown method returns an error reply; the hook never throws
 * across the socket.
 *
 * Note: `screenshot` needs the map created with `preserveDrawingBuffer: true`, or a WebGL
 * canvas reads back blank. See snippet.md.
 */
(function (global) {
  "use strict";

  // --- method -> MapLibre operation ----------------------------------------
  var HANDLERS = {
    get_viewport: function (map) {
      var c = map.getCenter();
      var b = map.getBounds();
      return {
        center: [c.lng, c.lat],
        zoom: map.getZoom(),
        bearing: map.getBearing(),
        pitch: map.getPitch(),
        bounds: b ? b.toArray() : null, // [[swLng,swLat],[neLng,neLat]]
      };
    },

    query_rendered_features: function (map, p) {
      p = p || {};
      var geom = _geometry(map, p); // undefined => whole viewport
      var opts = p.layers ? { layers: p.layers } : undefined;
      var feats = map.queryRenderedFeatures(geom, opts) || [];
      var limit = p.limit || 200;
      return { features: feats.slice(0, limit).map(_serializeFeature), truncated: feats.length > limit };
    },

    get_features_at: function (map, p) {
      var pt = map.project(_lngLat(p)); // geographic -> pixel
      var feats = map.queryRenderedFeatures(pt, p.layers ? { layers: p.layers } : undefined) || [];
      return { features: feats.map(_serializeFeature) };
    },

    click_at: function (map, p) {
      var lngLat = _lngLat(p);
      var pt = map.project(lngLat);
      // fire the map's own click so app handlers (popups, selection) run
      map.fire("click", { lngLat: lngLat, point: pt, originalEvent: {} });
      var feats = map.queryRenderedFeatures(pt, p.layers ? { layers: p.layers } : undefined) || [];
      return { features: feats.map(_serializeFeature), popup: _readPopup() };
    },

    read_popup: function () {
      return { popups: _readPopup() };
    },

    set_view: function (map, p) {
      p = p || {};
      if (p.bbox) {
        map.fitBounds(p.bbox, { animate: false });
      } else {
        var to = {};
        if (p.center) to.center = p.center;
        if (p.zoom != null) to.zoom = p.zoom;
        if (p.bearing != null) to.bearing = p.bearing;
        if (p.pitch != null) to.pitch = p.pitch;
        map.jumpTo(to);
      }
      return HANDLERS.get_viewport(map);
    },

    list_layers: function (map) {
      var layers = (map.getStyle() && map.getStyle().layers) || [];
      return {
        layers: layers.map(function (l) {
          var vis;
          try { vis = map.getLayoutProperty(l.id, "visibility"); } catch (e) { vis = undefined; }
          return { id: l.id, type: l.type, source: l.source, visibility: vis || "visible" };
        }),
      };
    },

    set_layer_visibility: function (map, p) {
      var vis = p.visible ? "visible" : "none";
      map.setLayoutProperty(p.layer, "visibility", vis);
      return { layer: p.layer, visibility: vis };
    },

    screenshot: function (map) {
      var canvas = map.getCanvas();
      var data;
      try { data = canvas.toDataURL("image/png"); } catch (e) { data = null; }
      if (!data || data.length < 64) {
        throw new Error("screenshot unavailable — create the map with preserveDrawingBuffer:true");
      }
      return { image: data, width: canvas.width, height: canvas.height };
    },
  };

  // --- helpers --------------------------------------------------------------
  function _lngLat(p) {
    if (!p || !p.point) throw new Error("expected params.point as [lng, lat]");
    return { lng: p.point[0], lat: p.point[1] };
  }

  function _geometry(map, p) {
    if (p.point) return map.project(_lngLat(p));
    if (p.bbox) {
      var sw = map.project({ lng: p.bbox[0][0], lat: p.bbox[0][1] });
      var ne = map.project({ lng: p.bbox[1][0], lat: p.bbox[1][1] });
      return [sw, ne];
    }
    return undefined;
  }

  function _serializeFeature(f) {
    return {
      id: f.id != null ? f.id : null,
      layer: f.layer ? f.layer.id : null,
      source: f.source != null ? f.source : null,
      sourceLayer: f.sourceLayer != null ? f.sourceLayer : null,
      properties: f.properties || {},
      geometryType: f.geometry ? f.geometry.type : null,
    };
  }

  function _readPopup() {
    var nodes = document.querySelectorAll(".maplibregl-popup-content, .mapboxgl-popup-content");
    return Array.prototype.map.call(nodes, function (n) {
      return (n.textContent || "").trim();
    });
  }

  // --- transport ------------------------------------------------------------
  function register(map, opts) {
    opts = opts || {};
    var url = opts.url || "ws://127.0.0.1:8765";
    var ws = new WebSocket(url);

    ws.onopen = function () {
      // U6: present the per-session token before commands are accepted.
      if (opts.token) ws.send(JSON.stringify({ type: "hello", token: opts.token }));
    };

    ws.onmessage = function (ev) {
      var req;
      try { req = JSON.parse(ev.data); } catch (e) { return; }
      if (!req || req.id == null) return;
      var reply = { id: req.id, ok: true, result: null };
      try {
        var handler = HANDLERS[req.method];
        if (!handler) {
          reply.ok = false;
          reply.error = "unknown method: " + req.method;
        } else {
          reply.result = handler(map, req.params || {});
        }
      } catch (e) {
        reply.ok = false;
        reply.error = String(e && e.message ? e.message : e);
      }
      ws.send(JSON.stringify(reply));
    };

    return ws;
  }

  global.mapMcp = { register: register, _handlers: HANDLERS };
})(typeof window !== "undefined" ? window : this);
