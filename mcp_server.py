"""
mcp_server.py
MCP (Model Context Protocol) Server — Traffic Signal Tools
COM6104 Group Project

Exposes TWO tools compliant with the MCP standard.
Run this server independently and test with the MCP Inspector:

    npx @modelcontextprotocol/inspector python mcp_server.py

Tools
-----
1. calculate_signal_timing   — Compute signal timing from traffic inputs.
2. restore_normal_signals    — Restore normal operation after accident clearance
                               (ESC / police override).
"""

import asyncio
import json
import sys
import os

# ---------------------------------------------------------------------------
# Ensure the project root is on the path when running from a subdirectory
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(__file__))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from signal_logic import calculate_signal_timing, parse_time, is_peak_hour

# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------
server = Server("traffic-signal-server")


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS = [
    types.Tool(
        name="calculate_signal_timing",
        description=(
            "Calculate adaptive traffic light timing for a four-way intersection "
            "based on queue lengths, current time, main-road designation, and "
            "any active accident. Returns green/red durations (in seconds) for "
            "the N-S axis and the E-W axis, along with status and explanatory notes."
        ),
        inputSchema={
            "type": "object",
            "required": ["main_roads", "queues", "time", "accident_direction"],
            "properties": {
                "main_roads": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["N", "S", "E", "W"]},
                    "description": (
                        "Directions that belong to the main road. "
                        "E.g. ['N','S'] means the north-south axis is the main road. "
                        "Pass all four directions if both axes are main roads."
                    ),
                },
                "queues": {
                    "type": "object",
                    "description": "Number of vehicles currently queued in each direction.",
                    "required": ["N", "S", "E", "W"],
                    "properties": {
                        "N": {"type": "integer", "minimum": 0},
                        "S": {"type": "integer", "minimum": 0},
                        "E": {"type": "integer", "minimum": 0},
                        "W": {"type": "integer", "minimum": 0},
                    },
                },
                "time": {
                    "type": "string",
                    "description": (
                        "Current time in 12-hour (e.g. '8:30 AM') or "
                        "24-hour (e.g. '08:30') format."
                    ),
                },
                "accident_direction": {
                    "type": "string",
                    "enum": ["N", "S", "E", "W", "C", "none"],
                    "description": (
                        "'N' or 'S' → accident on the N-S road; "
                        "'E' or 'W' → accident on the E-W road; "
                        "'C' → accident at the centre of the intersection; "
                        "'none' → no accident."
                    ),
                },
            },
        },
    ),
    types.Tool(
        name="restore_normal_signals",
        description=(
            "Restore normal (non-accident) traffic signal operation after "
            "an accident has been cleared by traffic police. "
            "Equivalent to the operator pressing ESC. "
            "Recalculates timing without any accident adjustment."
        ),
        inputSchema={
            "type": "object",
            "required": ["main_roads", "queues", "time"],
            "properties": {
                "main_roads": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["N", "S", "E", "W"]},
                    "description": "Directions that belong to the main road.",
                },
                "queues": {
                    "type": "object",
                    "description": "Current vehicle queue counts per direction.",
                    "required": ["N", "S", "E", "W"],
                    "properties": {
                        "N": {"type": "integer", "minimum": 0},
                        "S": {"type": "integer", "minimum": 0},
                        "E": {"type": "integer", "minimum": 0},
                        "W": {"type": "integer", "minimum": 0},
                    },
                },
                "time": {
                    "type": "string",
                    "description": "Current time in 12-hour or 24-hour format.",
                },
            },
        },
    ),
]


# ---------------------------------------------------------------------------
# Handler: list tools
# ---------------------------------------------------------------------------

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return TOOLS


# ---------------------------------------------------------------------------
# Handler: call tool
# ---------------------------------------------------------------------------

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:

    if name == "calculate_signal_timing":
        main_roads = arguments.get("main_roads", [])
        queues = arguments.get("queues", {"N": 0, "S": 0, "E": 0, "W": 0})
        time_str = arguments.get("time", "12:00")
        acc_dir = arguments.get("accident_direction", "none")

        result = calculate_signal_timing(
            main_roads=main_roads,
            queues=queues,
            time_str=time_str,
            accident_direction=acc_dir,
        )
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "restore_normal_signals":
        main_roads = arguments.get("main_roads", [])
        queues = arguments.get("queues", {"N": 0, "S": 0, "E": 0, "W": 0})
        time_str = arguments.get("time", "12:00")

        result = calculate_signal_timing(
            main_roads=main_roads,
            queues=queues,
            time_str=time_str,
            accident_direction="none",
        )
        result["restored"] = True
        result["note"] = (
            "✅ Normal operation restored. "
            "Accident override cleared by traffic police (ESC triggered)."
        )
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    else:
        error = {"error": f"Unknown tool: {name}"}
        return [types.TextContent(type="text", text=json.dumps(error))]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
