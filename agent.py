"""
agent.py
LLM-TrafficBrain Agent — Main Entry Point
COM6104 Group Project

Architecture (based on Paper 0379 — LLM-TrafficBrain):
  1. Traffic state is collected from the user via structured prompts.
  2. The state is encoded into a natural-language prompt for the LLM.
  3. The LLM (Claude via Anthropic API / Bedrock) reasons about the
     traffic conditions and calls MCP-standard tools.
  4. Tool results are interpreted and returned to the user.
  5. Short-term memory retains recent states so the LLM can reason
     across multiple cycles without retraining.

Run:
    python agent.py

ESC Override (accident mode):
    While the system is in accident mode, type  esc  and press Enter
    at any input prompt to restore normal operation.
"""

import json
import os
import sys
import re

import anthropic
from dotenv import load_dotenv

from memory import ConversationMemory
from signal_logic import calculate_signal_timing, parse_time

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

API_KEY = os.getenv(
    "ANTHROPIC_API_KEY",
    "ABSKQmVkcm9ja0FQSUtleS1lcnNqLWF0LTQ5MTkxOTM3NTA5Nzo1QzdtTEY2dm0yeUlwS2FkTzFPeksvNnlDYmhKc0pZWUE3UHZqdlJ1QjE2dkJDd0hJWGJxbkpVYTAxND0=",
)
BASE_URL = os.getenv("ANTHROPIC_BASE_URL", None)          # Set if using a Bedrock proxy
MODEL    = os.getenv("MODEL", "claude-3-5-sonnet-20241022")

# Build client — supports both direct Anthropic API and Bedrock-compatible proxies
client = anthropic.Anthropic(
    api_key=API_KEY,
    **({"base_url": BASE_URL} if BASE_URL else {}),
)

# ---------------------------------------------------------------------------
# Tool definitions (mirror MCP server schemas for Anthropic tool-use API)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "calculate_signal_timing",
        "description": (
            "Calculate adaptive traffic light timing for a four-way intersection "
            "based on queue lengths, current time, main-road designation, and "
            "any active accident. Returns green/red durations in seconds for "
            "the N-S axis and the E-W axis, with status and explanatory notes."
        ),
        "input_schema": {
            "type": "object",
            "required": ["main_roads", "queues", "time", "accident_direction"],
            "properties": {
                "main_roads": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["N", "S", "E", "W"]},
                    "description": "Directions that belong to the main road.",
                },
                "queues": {
                    "type": "object",
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
                "accident_direction": {
                    "type": "string",
                    "enum": ["N", "S", "E", "W", "C", "none"],
                    "description": (
                        "N/S → accident on N-S road; "
                        "E/W → accident on E-W road; "
                        "C → centre blockage; "
                        "none → no accident."
                    ),
                },
            },
        },
    },
    {
        "name": "restore_normal_signals",
        "description": (
            "Restore normal traffic signal operation after an accident has been "
            "cleared by traffic police (ESC override). "
            "Recalculates timing without any accident adjustment."
        ),
        "input_schema": {
            "type": "object",
            "required": ["main_roads", "queues", "time"],
            "properties": {
                "main_roads": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["N", "S", "E", "W"]},
                },
                "queues": {
                    "type": "object",
                    "required": ["N", "S", "E", "W"],
                    "properties": {
                        "N": {"type": "integer", "minimum": 0},
                        "S": {"type": "integer", "minimum": 0},
                        "E": {"type": "integer", "minimum": 0},
                        "W": {"type": "integer", "minimum": 0},
                    },
                },
                "time": {"type": "string"},
            },
        },
    },
]

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are LLM-TrafficBrain, an intelligent traffic signal control assistant
for a four-way urban intersection. Your role is to:

1. Interpret structured traffic state data provided by the operator.
2. Call the appropriate tool (calculate_signal_timing or restore_normal_signals)
   with the correct parameters extracted from the conversation.
3. Interpret the tool result and present it clearly to the operator.

Always present the final output in the following structured format:

  ┌─────────────────────────────────────────────┐
  │  N→S:  green_light: __ s   red_light: __ s  │
  │  E→W:  green_light: __ s   red_light: __ s  │
  └─────────────────────────────────────────────┘
  Peak period : Yes / No
  Status      : NORMAL / ACCIDENT MODE
  Note        : <brief explanation of the decision>

If the operator indicates that traffic police have arrived and cleared the scene
(or types ESC), call restore_normal_signals to return to normal operation.

Keep responses professional, concise, and in English.
"""

# ---------------------------------------------------------------------------
# Tool execution (calls signal_logic.py directly — mirrors MCP server logic)
# ---------------------------------------------------------------------------

def execute_tool(name: str, arguments: dict) -> str:
    """Execute a tool call and return the result as a JSON string."""
    if name == "calculate_signal_timing":
        result = calculate_signal_timing(
            main_roads=arguments.get("main_roads", []),
            queues=arguments.get("queues", {"N": 0, "S": 0, "E": 0, "W": 0}),
            time_str=arguments.get("time", "12:00"),
            accident_direction=arguments.get("accident_direction", "none"),
        )
        return json.dumps(result, indent=2)

    elif name == "restore_normal_signals":
        result = calculate_signal_timing(
            main_roads=arguments.get("main_roads", []),
            queues=arguments.get("queues", {"N": 0, "S": 0, "E": 0, "W": 0}),
            time_str=arguments.get("time", "12:00"),
            accident_direction="none",
        )
        result["restored"] = True
        result["note"] = (
            "✅ Normal operation restored. "
            "Accident override cleared by traffic police (ESC triggered)."
        )
        return json.dumps(result, indent=2)

    return json.dumps({"error": f"Unknown tool: {name}"})


# ---------------------------------------------------------------------------
# LLM call with agentic tool-use loop
# ---------------------------------------------------------------------------

def call_llm_with_tools(memory: ConversationMemory, user_input: str) -> str:
    """
    Send user_input to the LLM with full conversation history and tools.
    Handles multi-turn tool-use loop automatically.
    Returns the final assistant text response.
    """
    memory.add_user_message(user_input)

    # Build message list: inject memory context into system prompt
    context_summary = memory.build_context_summary()
    system = SYSTEM_PROMPT + f"\n\n[Memory Context]\n{context_summary}"

    messages = memory.get_messages()

    max_iterations = 6  # Safety limit for tool-use loop
    for _ in range(max_iterations):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

        # Collect the full content block list from the response
        content_blocks = response.content

        if response.stop_reason == "end_turn":
            # No more tool calls — extract final text
            text = " ".join(
                b.text for b in content_blocks if hasattr(b, "text")
            ).strip()
            memory.add_assistant_message(text)
            return text

        if response.stop_reason == "tool_use":
            # Append assistant message with tool_use blocks
            messages.append({"role": "assistant", "content": content_blocks})

            # Execute each tool call and collect results
            tool_result_content = []
            for block in content_blocks:
                if block.type == "tool_use":
                    tool_output = execute_tool(block.name, block.input)

                    # Update memory state if this was a signal calculation
                    if block.name in ("calculate_signal_timing", "restore_normal_signals"):
                        parsed = json.loads(tool_output)
                        latest = memory.get_latest_state()
                        main_roads = block.input.get("main_roads", [])
                        queues = block.input.get("queues", {})
                        time_str = block.input.get("time", "12:00")
                        memory.record_state(main_roads, queues, time_str, parsed)

                        if parsed.get("restored") or not parsed.get("accident_mode"):
                            memory.clear_accident()

                    tool_result_content.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": tool_output,
                    })

            # Append tool results and continue the loop
            messages.append({"role": "user", "content": tool_result_content})

        else:
            # Unexpected stop reason — return whatever text is available
            text = " ".join(
                b.text for b in content_blocks if hasattr(b, "text")
            ).strip()
            memory.add_assistant_message(text)
            return text

    return "⚠  Maximum tool-call iterations reached. Please try again."


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------

ESC_KEYWORDS = {'esc', 'escape', 'restore', 'clear', 'normal', 'override'}


def check_esc(text: str) -> bool:
    """Return True if the user's input looks like an ESC/restore command."""
    return text.strip().lower() in ESC_KEYWORDS


def prompt_input(label: str, memory: ConversationMemory) -> str:
    """Display a prompt and check for ESC at every input point."""
    value = input(label).strip()
    if check_esc(value) and memory.accident_active:
        raise EscapeSignal
    return value


class EscapeSignal(Exception):
    """Raised when the operator triggers an ESC / police override."""


# ---------------------------------------------------------------------------
# Structured input collection
# ---------------------------------------------------------------------------

def collect_intersection_inputs(memory: ConversationMemory) -> dict:
    """
    Interactively collect all required intersection inputs from the operator.
    Returns a dict ready to be embedded in a natural-language prompt.
    """
    print()
    print("=" * 60)
    print("  TRAFFIC INTERSECTION — INPUT PANEL")
    print("=" * 60)
    if memory.accident_active:
        print("  ⚠  ACCIDENT MODE ACTIVE  |  Type 'ESC' to restore")
    print()

    # --- Main road direction ---
    while True:
        raw = prompt_input(
            "  Main road direction(s) [e.g. N->S  or  E->W  or  N->S,E->W]: ",
            memory,
        )
        dirs = re.findall(r'[NSEW]', raw.upper())
        if dirs:
            main_roads = list(set(dirs))
            break
        print("  ⚠  Please enter valid directions (N, S, E, W).")

    # --- Queue counts ---
    queues = {}
    for direction in ['N', 'S', 'E', 'W']:
        while True:
            raw = prompt_input(
                f"  Queue length — {direction} (number of vehicles): ",
                memory,
            )
            try:
                queues[direction] = int(raw)
                break
            except ValueError:
                print("  ⚠  Please enter an integer.")

    # --- Time ---
    while True:
        raw = prompt_input(
            "  Current time [e.g. 8:30 AM  or  20:30]: ",
            memory,
        )
        try:
            parse_time(raw)   # Validate format
            time_str = raw
            break
        except ValueError as exc:
            print(f"  ⚠  {exc}")

    # --- Accident ---
    accident_direction = "none"
    raw_event = prompt_input(
        "  Any accident? [none / yes / yeah]: ",
        memory,
    )

    if raw_event.strip().lower() in ('yes', 'yeah', 'y'):
        raw_acc = prompt_input(
            "  Accident direction [N / S / E / W / C]: ",
            memory,
        )
        acc = raw_acc.strip().upper()
        if acc in ('N', 'S', 'E', 'W', 'C'):
            accident_direction = acc
        else:
            print("  ⚠  Invalid direction — treating as no accident.")

    return {
        "main_roads": main_roads,
        "queues": queues,
        "time": time_str,
        "accident_direction": accident_direction,
    }


# ---------------------------------------------------------------------------
# Prompt builder (Paper 0379 style — structured state → natural language)
# ---------------------------------------------------------------------------

def build_natural_language_prompt(inputs: dict) -> str:
    """
    Translate structured traffic state data into a natural-language prompt
    (following the LLM-TrafficBrain methodology from Paper 0379).
    """
    main = ", ".join(inputs["main_roads"])
    q = inputs["queues"]
    t = inputs["time"]
    acc = inputs["accident_direction"]

    queue_desc = (
        f"{q['N']} vehicles queued to the north, "
        f"{q['S']} to the south, "
        f"{q['E']} to the east, "
        f"and {q['W']} to the west"
    )

    acc_desc = (
        "No accidents are reported."
        if acc.lower() == "none"
        else f"An accident has been reported: direction '{acc}'."
    )

    prompt = (
        f"Current intersection state at {t}: "
        f"The designated main road direction(s) are: {main}. "
        f"There are {queue_desc}. "
        f"{acc_desc} "
        f"Please calculate the optimal traffic signal timing and explain your decision."
    )
    return prompt


# ---------------------------------------------------------------------------
# Main interaction loop
# ---------------------------------------------------------------------------

def main() -> None:
    memory = ConversationMemory(max_turns=10, max_states=5)

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║          LLM-TrafficBrain  —  Signal Control Agent       ║")
    print("║          COM6104  |  Hang Seng University of Hong Kong   ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()
    print("  Type 'exit' or 'quit' at any prompt to end the session.")
    print("  Type 'ESC' at any prompt while in accident mode to restore")
    print("  normal operation (simulates traffic police override).")
    print()

    while True:
        try:
            # Collect structured inputs
            inputs = collect_intersection_inputs(memory)

        except EscapeSignal:
            # ---- ESC override triggered ----
            print()
            print("  🚔  Traffic police override activated — restoring normal operation...")
            latest = memory.get_latest_state()
            if latest:
                esc_prompt = (
                    f"Traffic police have arrived and cleared the accident. "
                    f"Please restore normal signal operation. "
                    f"Main roads: {latest['main_roads']}. "
                    f"Current queues: {latest['queues']}. "
                    f"Time: {latest['time']}."
                )
            else:
                esc_prompt = (
                    "Traffic police have cleared the scene. "
                    "Please restore normal signal operation for the intersection."
                )
            response = call_llm_with_tools(memory, esc_prompt)
            memory.clear_accident()
            print()
            print(response)
            print()
            continue

        except (KeyboardInterrupt, EOFError):
            print("\n\n  Session ended. Goodbye.\n")
            sys.exit(0)

        # Check for exit at any input
        flat_vals = " ".join(str(v) for v in inputs.values())
        if flat_vals.strip().lower() in ('exit', 'quit'):
            print("\n  Session ended. Goodbye.\n")
            break

        # Build natural-language prompt (Paper 0379 methodology)
        nl_prompt = build_natural_language_prompt(inputs)

        print()
        print("  ⏳  Analysing traffic conditions...")
        print()

        try:
            response = call_llm_with_tools(memory, nl_prompt)
        except anthropic.APIError as exc:
            print(f"  ⚠  API error: {exc}")
            continue

        print(response)
        print()

        # Ask whether to run another cycle or exit
        again = input("  ▶  Run another cycle? [Enter to continue / 'exit' to quit]: ").strip().lower()
        if again in ('exit', 'quit', 'q', 'n', 'no'):
            print("\n  Session ended. Goodbye.\n")
            break


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
