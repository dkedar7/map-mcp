"""Example: a LangChain agent drives a live MapLibre map through map-mcp.

A langgraph ReAct agent (on any tool-capable model, here via OpenRouter) is given three
map-mcp operations as tools and asked to find the most-populous visible city and navigate to
it. The agent acts on the *same* live map a human is looking at — perception (what's rendered)
and control (pan/zoom/click) go through map-mcp's real operation layer.

Run (needs the demo extra + an OpenRouter key):

    export OPENROUTER_API_KEY=sk-or-...
    uv run --extra demo python examples/langchain_agent.py

Optional env:
    OPENROUTER_MODEL   model slug (default: anthropic/claude-sonnet-4.6)
    MAPMCP_RECORD_DIR  if set, record a .webm of the run into this directory
    MAPMCP_SHOT        screenshot output path (default: map-mcp-agent-demo.png)

This drives a real browser, so it needs a Chromium (`playwright install chromium`).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

for _s in (sys.stdout, sys.stderr):  # the agent's reply may contain emoji
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from map_mcp.bridge import Bridge
from map_mcp.coreops import CoreOps

TOKEN = "demo-token-7f3a"
PORT = 8765
SAMPLE = (Path(__file__).parent / "sample_app" / "index.html").resolve()
SAMPLE_URL = f"{SAMPLE.as_uri()}?token={TOKEN}"
SHOT = os.environ.get("MAPMCP_SHOT", "map-mcp-agent-demo.png")
MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.6")
RECORD_DIR = os.environ.get("MAPMCP_RECORD_DIR")

if not os.environ.get("OPENROUTER_API_KEY"):
    sys.exit("Set OPENROUTER_API_KEY (an OpenRouter key) to run this example.")

bridge = Bridge()
bridge.serve_ws(host="127.0.0.1", port=PORT, token=TOKEN)
print(f"bridge listening on 127.0.0.1:{bridge.port}", flush=True)
ops = CoreOps(bridge)

# --- map-mcp operations exposed as LangChain tools ---
from langchain_core.tools import tool


@tool
def query_rendered_features() -> str:
    """Return the features currently rendered on the live map, with their properties."""
    return json.dumps(ops.query_rendered_features())


@tool
def set_view(lng: float, lat: float, zoom: float) -> str:
    """Center the live map on [lng, lat] at the given zoom level."""
    return json.dumps(ops.set_view(center=[lng, lat], zoom=zoom))


@tool
def click_at(lng: float, lat: float) -> str:
    """Click the live map at [lng, lat]; opens the feature's popup and returns it."""
    return json.dumps(ops.click_at([lng, lat]))


TOOLS = [query_rendered_features, set_view, click_at]

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

llm = ChatOpenAI(
    model=MODEL,
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
    temperature=0,
    default_headers={"HTTP-Referer": "https://github.com/dkedar7/map-mcp",
                     "X-Title": "map-mcp example"},
)
agent = create_react_agent(llm, TOOLS)

TASK = (
    "You are connected to a LIVE interactive map of European cities. The map may be zoomed "
    "in, so first call set_view(lng=13, lat=47, zoom=3) to bring all cities into view. Then: "
    "(1) call query_rendered_features to see the cities and their populations; "
    "(2) determine which city has the LARGEST population; "
    "(3) set_view to center on that city at zoom 8; "
    "(4) click_at that city to open its popup. "
    "Finish by stating which city you chose and its population. Keep prose plain (no emoji)."
)

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx_kwargs = {"viewport": {"width": 1000, "height": 640}}
    if RECORD_DIR:
        Path(RECORD_DIR).mkdir(parents=True, exist_ok=True)
        ctx_kwargs["record_video_dir"] = RECORD_DIR
        ctx_kwargs["record_video_size"] = {"width": 1000, "height": 640}
    ctx = browser.new_context(**ctx_kwargs)
    page = ctx.new_page()
    page.goto(SAMPLE_URL, timeout=20000)

    deadline = time.time() + 20
    while not bridge.connected and time.time() < deadline:
        page.wait_for_timeout(200)
    print("hook connected:", bridge.connected, flush=True)
    if not bridge.connected:
        ctx.close(); browser.close()
        sys.exit("ERROR: the map hook never connected to the bridge")
    page.wait_for_timeout(3500)  # lead-in: let CDN tiles render

    print(f"\n--- running agent on {MODEL} ---", flush=True)
    result = agent.invoke({"messages": [{"role": "user", "content": TASK}]})

    for m in result["messages"]:
        tcs = getattr(m, "tool_calls", None)
        if tcs:
            for tc in tcs:
                print(f"  TOOL  {tc['name']}({tc['args']})", flush=True)
        elif m.__class__.__name__ == "ToolMessage":
            print(f"   ->   {str(m.content)[:110]}", flush=True)
        elif m.__class__.__name__ == "AIMessage" and m.content:
            print(f"  AGENT: {str(m.content)[:400]}", flush=True)

    page.wait_for_timeout(2500)  # tail: let the popup linger for the recording
    page.screenshot(path=SHOT)
    print("\nscreenshot ->", SHOT, flush=True)
    video = page.video.path() if RECORD_DIR else None
    ctx.close()   # flushes the video
    browser.close()
    if video:
        print("video ->", video, flush=True)
