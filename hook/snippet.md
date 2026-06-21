# Adding the map-mcp hook to your MapLibre app

map-mcp drives an **existing** map — you add one snippet so it can reach your live map
instance. Cooperation is required (v1); a no-cooperation path is deferred.

## 1. Start the bridge

```
map-mcp serve
```

It prints a `ws://127.0.0.1:<port>` URL and a **per-session token** (the token gate is
local-only security — only a page presenting it can drive your map).

## 2. Add the hook to your page

```html
<script src="map-mcp-hook.js"></script>
<script>
  // `map` is your existing maplibregl.Map instance.
  mapMcp.register(map, { url: "ws://127.0.0.1:8765", token: "PASTE_TOKEN_FROM_SERVE" });
</script>
```

That's it. The agent (over MCP) and the `map-mcp` CLI now act on the same map you're looking at.

## Notes

- **Screenshots** need the map created with `preserveDrawingBuffer: true`:
  ```js
  const map = new maplibregl.Map({ /* ... */, preserveDrawingBuffer: true });
  ```
  Without it, a WebGL canvas reads back blank and the `screenshot` tool returns an error.
- Geographic inputs (`point`, `bbox`, `center`) are `[lng, lat]`. The hook projects them to
  pixels for `queryRenderedFeatures` itself.
- The hook never creates a map and never posts anywhere — it answers read/drive requests on the
  loopback socket only.
