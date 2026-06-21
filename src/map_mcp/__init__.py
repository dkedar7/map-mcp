"""map-mcp — drive and perceive an existing live MapLibre GL map from an agent or a human CLI.

A map app opts in with a small JS hook that registers its live map and connects out to a
local WebSocket this process runs. The MCP tools (for agents) and the CLI (for humans) are
thin frontends over one shared core-operations layer, so any operation one can do, the other
can too (parity by construction). v1 is MapLibre-only and drives *existing* maps — it does not
generate maps.
"""

__version__ = "0.1.0"
