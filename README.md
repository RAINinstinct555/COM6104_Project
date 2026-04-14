# LLM-TrafficBrain — COM6104 Group Project

**An LLM-Driven Adaptive Traffic Signal Control Agent**

> Reference paper: *LLM-TrafficBrain: An Information-Centric Framework for Dynamic Signal Control with Large Language Models* (Paper 0379)

---

## Project Overview

This agent simulates adaptive traffic signal control for a four-way urban intersection. It follows the LLM-TrafficBrain architecture described in Paper 0379:

1. **Traffic state representation** — queue lengths, time context, and special events are collected.
2. **Semantic prompt construction** — structured data is translated into natural language.
3. **LLM reasoning** — Claude (via Anthropic API) acts as the intelligent scheduling agent.
4. **Tool-based execution** — two MCP-standard tools compute the exact signal timing.
5. **Short-term memory** — recent states are retained so the LLM can reason across control cycles.

---

## Repository Structure

```
traffic-signal-agent/
├── agent.py          # Main interactive agent (LLM + memory + tool-use loop)
├── mcp_server.py     # MCP-compliant server (two tools, testable with MCP Inspector)
├── signal_logic.py   # Pure signal timing calculation logic
├── memory.py         # Short-term memory module
├── requirements.txt
└── README.md
```

---

## Setup

### 1. Clone the repository

```bash
git clone <your-github-repo-url>
cd traffic-signal-agent
```

### 2. Create and activate a virtual environment (recommended)

```bash
python -m venv venv
# macOS / Linux:
source venv/bin/activate
# Windows:
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```env
# Anthropic API key (or Bedrock-compatible key)
ANTHROPIC_API_KEY=<your-api-key>

# Optional: set if using a Bedrock gateway with a custom base URL
# ANTHROPIC_BASE_URL=https://your-bedrock-endpoint

# Optional: override the model (default: claude-3-5-sonnet-20241022)
# MODEL=claude-3-5-sonnet-20241022
```

---

## Running the Agent

```bash
python agent.py
```

The agent will prompt you for:

| Input | Description |
|-------|-------------|
| **Main road direction(s)** | e.g. `N->S` or `E->W` or `N->S,E->W` for both |
| **Queue lengths** | Number of vehicles waiting in each direction (N, S, E, W) |
| **Time** | 12-hour (`8:30 AM`) or 24-hour (`08:30`) format |
| **Accident** | `none` / `yes` — if yes, specify direction: `N`, `S`, `E`, `W`, or `C` |

### ESC Override (Accident Mode)

When an accident is active, type **`ESC`** at any input prompt to simulate traffic police arriving on scene and restoring normal operation.

---

## Running the MCP Server (for MCP Inspector testing)

```bash
python mcp_server.py
```

Test with the MCP Inspector:

```bash
npx @modelcontextprotocol/inspector python mcp_server.py
```

### Tools exposed by the MCP server

| Tool | Description |
|------|-------------|
| `calculate_signal_timing` | Computes optimal green/red durations for N-S and E-W axes |
| `restore_normal_signals` | Restores normal timing after police clear an accident (ESC) |

---

## Traffic Signal Logic Summary

### Base timing

| Road type | Period | Green | Red |
|-----------|--------|-------|-----|
| Main road | Off-peak | 30 s | 70 s |
| Main road | Peak | 50 s | 60 s |
| Non-main | Off-peak | 35 s | 90 s |
| Non-main | Peak | 45 s | 80 s |

Peak periods: **07:00–09:30** (morning) and **18:00–20:30** (evening).

### Queue-based adjustment (off-peak)

| Queue | Green | Red |
|-------|-------|-----|
| > 20 | +10 s | — |
| > 30 | +20 s | — |
| > 50 | +30 s | −10 s |

### Queue-based adjustment (peak)

| Queue | Green | Red |
|-------|-------|-----|
| > 20 | +10 s | −5 s |
| > 30 | +20 s | −10 s |
| > 50 | +30 s | — |

### Accident adjustments

| Scenario | Effect |
|----------|--------|
| N/S road accident | EW green +15 s; NS green +5 s (off-peak) / +10 s (peak) |
| E/W road accident | NS green +15 s; EW green +5 s (off-peak) / +10 s (peak) |
| Centre (C) blockage | All signals **RED 15 s**, green = NULL; after clearance: main +10 s, non-main +5 s |

---

## Agent Architecture

```
User Input
    │
    ▼
ConversationMemory (short-term)
    │
    ▼
Natural Language Prompt (LLM-TrafficBrain style)
    │
    ▼
Claude LLM  ──tool_use──►  calculate_signal_timing
    │                 └──►  restore_normal_signals
    │
    ▼
Signal Timing Output  →  Display to Operator
    │
    ▼
Memory Updated  →  Next Control Cycle
```

---

## Marking Criteria Compliance

| Criterion | Implementation |
|-----------|---------------|
| **Two distinct tools** | `calculate_signal_timing` + `restore_normal_signals` |
| **MCP standard** | `mcp_server.py` — testable with MCP Inspector |
| **Short-term memory** | `ConversationMemory` class in `memory.py` |
| **GitHub** | All source code in this repository |
| **LLM integration** | Claude via Anthropic API with tool-use loop |
| **Agentic reasoning** | Multi-step tool-use loop; context-aware decisions |

---

## Demo

*(Insert demo video link here)*

---

## References

Yan, J., Li, D., & Yang, Q. (2025). *LLM-TrafficBrain: An Information-Centric Framework for Dynamic Signal Control with Large Language Models*. Hang Seng University of Hong Kong / Xi'an Jiaotong University.
