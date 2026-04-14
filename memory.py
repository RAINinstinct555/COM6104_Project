"""
memory.py
Short-Term Memory Module for the Traffic Signal Agent
COM6104 Group Project

Maintains a sliding window of recent conversation turns and
intersection-state snapshots so the LLM always has relevant context.
"""

from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional


class ConversationMemory:
    """
    Stores recent conversation turns (user + assistant messages) and
    a separate log of intersection state snapshots.

    Parameters
    ----------
    max_turns : int
        Maximum number of conversation turns to retain (default 10).
    max_states : int
        Maximum number of intersection state snapshots to retain (default 5).
    """

    def __init__(self, max_turns: int = 10, max_states: int = 5) -> None:
        self._turns: deque = deque(maxlen=max_turns)
        self._states: deque = deque(maxlen=max_states)
        self._accident_active: bool = False
        self._accident_context: Optional[Dict] = None

    # ------------------------------------------------------------------
    # Conversation turns
    # ------------------------------------------------------------------

    def add_user_message(self, content: str) -> None:
        """Append a user message to memory."""
        self._turns.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str) -> None:
        """Append an assistant message to memory."""
        self._turns.append({"role": "assistant", "content": content})

    def get_messages(self) -> List[Dict[str, str]]:
        """Return the current message history as a list of role/content dicts."""
        return list(self._turns)

    def clear_messages(self) -> None:
        """Clear all stored conversation turns."""
        self._turns.clear()

    # ------------------------------------------------------------------
    # Intersection state snapshots
    # ------------------------------------------------------------------

    def record_state(
        self,
        main_roads: List[str],
        queues: Dict[str, int],
        time_str: str,
        result: Dict[str, Any],
    ) -> None:
        """
        Save a snapshot of the intersection state after a calculation.

        Parameters
        ----------
        main_roads : list[str]  Directions designated as main road.
        queues     : dict       Vehicle queue counts per direction.
        time_str   : str        Time string used for the calculation.
        result     : dict       Output from calculate_signal_timing().
        """
        snapshot = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "main_roads": main_roads,
            "queues": queues,
            "time": time_str,
            "result": result,
        }
        self._states.append(snapshot)

        # Keep accident context up to date
        if result.get("accident_mode"):
            self._accident_active = True
            self._accident_context = snapshot
        else:
            self._accident_active = False
            self._accident_context = None

    def get_state_history(self) -> List[Dict]:
        """Return all stored intersection state snapshots."""
        return list(self._states)

    def get_latest_state(self) -> Optional[Dict]:
        """Return the most recent intersection state snapshot, or None."""
        return self._states[-1] if self._states else None

    # ------------------------------------------------------------------
    # Accident tracking
    # ------------------------------------------------------------------

    @property
    def accident_active(self) -> bool:
        """True if the latest state contains an active accident."""
        return self._accident_active

    def clear_accident(self) -> None:
        """Mark the accident as cleared (called when ESC / override is triggered)."""
        self._accident_active = False
        self._accident_context = None

    # ------------------------------------------------------------------
    # Context summary for LLM prompt injection
    # ------------------------------------------------------------------

    def build_context_summary(self) -> str:
        """
        Build a concise natural-language summary of recent memory
        to prepend to the system prompt so the LLM has context.
        """
        lines: List[str] = []

        latest = self.get_latest_state()
        if latest:
            r = latest["result"]
            ns = r.get("ns", {})
            ew = r.get("ew", {})
            lines.append(
                f"[Last calculation at {latest['time']}] "
                f"N-S: green={ns.get('green')} s, red={ns.get('red')} s | "
                f"E-W: green={ew.get('green')} s, red={ew.get('red')} s | "
                f"Peak={r.get('is_peak')} | Status={r.get('status')}"
            )

        if self._accident_active and self._accident_context:
            lines.append(
                f"[ACCIDENT ACTIVE] Mode: {self._accident_context['result'].get('accident_mode')}. "
                "Awaiting traffic police override (ESC)."
            )

        if not lines:
            return "No previous intersection data available."
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"ConversationMemory("
            f"turns={len(self._turns)}, "
            f"states={len(self._states)}, "
            f"accident_active={self._accident_active})"
        )
