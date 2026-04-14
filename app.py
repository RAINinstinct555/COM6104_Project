"""
app.py
Flask Web Server — LLM-TrafficBrain Visual Interface
COM6104 Group Project
"""

import json
import os
import sys
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import anthropic

sys.path.insert(0, os.path.dirname(__file__))
from signal_logic import calculate_signal_timing, parse_time
from memory import ConversationMemory

load_dotenv()

app = Flask(__name__)

API_KEY = os.getenv(
    "ANTHROPIC_API_KEY",
    "ABSKQmVkcm9ja0FQSUtleS1lcnNqLWF0LTQ5MTkxOTM3NTA5Nzo1QzdtTEY2dm0yeUlwS2FkTzFPeksvNnlDYmhKc0pZWUE3UHZqdlJ1QjE2dkJDd0hJWGJxbkpVYTAxND0=",
)
MODEL = os.getenv("MODEL", "claude-3-5-sonnet-20241022")

client = anthropic.Anthropic(api_key=API_KEY)
memory = ConversationMemory(max_turns=10, max_states=5)

TOOLS = [
    {
        "name": "calculate_signal_timing",
        "description": (
            "Calculate adaptive traffic light timing for a four-way intersection "
            "based on queue lengths, current time, main-road designation, and "
            "any active accident."
        ),
        "input_schema": {
            "type": "object",
            "required": ["main_roads", "queues", "time", "accident_direction"],
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
                "accident_direction": {
                    "type": "string",
                    "enum": ["N", "S", "E", "W", "C", "none"],
                },
            },
        },
    },
    {
        "name": "restore_normal_signals",
        "description": "Restore normal traffic signal operation after accident clearance (ESC override).",
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

SYSTEM_PROMPT = """You are LLM-TrafficBrain, an intelligent traffic signal control assistant.
Analyse the traffic conditions and call calculate_signal_timing with the correct parameters.
After getting the result, provide a concise explanation (2-3 sentences) of your decision in English.
Focus on WHY the timing was set this way — mention peak hours, queue levels, or accident handling.
Keep it professional and brief."""


def execute_tool(name, arguments):
    if name == "calculate_signal_timing":
        result = calculate_signal_timing(
            main_roads=arguments.get("main_roads", []),
            queues=arguments.get("queues", {"N": 0, "S": 0, "E": 0, "W": 0}),
            time_str=arguments.get("time", "12:00"),
            accident_direction=arguments.get("accident_direction", "none"),
        )
        return result
    elif name == "restore_normal_signals":
        result = calculate_signal_timing(
            main_roads=arguments.get("main_roads", []),
            queues=arguments.get("queues", {"N": 0, "S": 0, "E": 0, "W": 0}),
            time_str=arguments.get("time", "12:00"),
            accident_direction="none",
        )
        result["restored"] = True
        return result
    return {"error": f"Unknown tool: {name}"}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/calculate", methods=["POST"])
def calculate():
    data = request.json
    main_roads = data.get("main_roads", [])
    queues = data.get("queues", {"N": 0, "S": 0, "E": 0, "W": 0})
    time_str = data.get("time", "12:00")
    accident = data.get("accident", "none")

    # Build natural language prompt
    q = queues
    acc_desc = "No accidents reported." if accident.lower() == "none" else f"Accident reported at direction '{accident}'."
    nl_prompt = (
        f"Intersection state at {time_str}: "
        f"Main roads: {', '.join(main_roads)}. "
        f"Queues — North: {q.get('N',0)}, South: {q.get('S',0)}, "
        f"East: {q.get('E',0)}, West: {q.get('W',0)} vehicles. "
        f"{acc_desc} Calculate optimal signal timing."
    )

    memory.add_user_message(nl_prompt)
    context = memory.build_context_summary()
    system = SYSTEM_PROMPT + f"\n\n[Memory Context]\n{context}"
    messages = memory.get_messages()

    signal_result = None
    llm_explanation = ""

    try:
        for _ in range(5):
            response = client.messages.create(
                model=MODEL,
                max_tokens=512,
                system=system,
                tools=TOOLS,
                messages=messages,
            )
            content_blocks = response.content

            if response.stop_reason == "end_turn":
                llm_explanation = " ".join(
                    b.text for b in content_blocks if hasattr(b, "text")
                ).strip()
                memory.add_assistant_message(llm_explanation)
                break

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": content_blocks})
                tool_results = []
                for block in content_blocks:
                    if block.type == "tool_use":
                        tool_output = execute_tool(block.name, block.input)
                        if signal_result is None:
                            signal_result = tool_output
                            memory.record_state(main_roads, queues, time_str, tool_output)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(tool_output),
                        })
                messages.append({"role": "user", "content": tool_results})

    except Exception as e:
        # Fallback: calculate directly without LLM
        signal_result = calculate_signal_timing(
            main_roads=main_roads,
            queues=queues,
            time_str=time_str,
            accident_direction=accident,
        )
        llm_explanation = f"Signal timing calculated based on traffic rules. (LLM error: {str(e)})"

    if signal_result is None:
        signal_result = calculate_signal_timing(
            main_roads=main_roads,
            queues=queues,
            time_str=time_str,
            accident_direction=accident,
        )

    return jsonify({
        "signal": signal_result,
        "explanation": llm_explanation,
        "history": memory.get_state_history(),
    })


@app.route("/api/restore", methods=["POST"])
def restore():
    data = request.json
    latest = memory.get_latest_state()
    if latest:
        result = calculate_signal_timing(
            main_roads=latest["main_roads"],
            queues=latest["queues"],
            time_str=latest["time"],
            accident_direction="none",
        )
        result["restored"] = True
        memory.clear_accident()
        memory.record_state(latest["main_roads"], latest["queues"], latest["time"], result)
        return jsonify({"signal": result, "explanation": "✅ Normal operation restored by traffic police override."})
    return jsonify({"error": "No previous state found"}), 400


@app.route("/api/memory", methods=["GET"])
def get_memory():
    return jsonify({
        "history": memory.get_state_history(),
        "accident_active": memory.accident_active,
        "summary": memory.build_context_summary(),
    })


if __name__ == "__main__":
    app.run(debug=True, port=5001)
