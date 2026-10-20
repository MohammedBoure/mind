"""Custom Textual messages for decoupled UI-backend communication.

These messages form the contract between the UI layer and the backend.
The UI emits and listens for these messages; the backend (or mock layer)
posts them. This ensures the UI never directly imports backend logic.
"""

from __future__ import annotations

from textual.message import Message

from mind.state.models import InterAgentMessage, LogEntry


class AgentLogAppend(Message):
    """A new log entry was produced by an agent."""

    def __init__(self, agent_id: int, entry: LogEntry) -> None:
        super().__init__()
        self.agent_id = agent_id
        self.entry = entry


class AgentStatusChanged(Message):
    """An agent's operational status changed."""

    def __init__(self, agent_id: int, new_status: str) -> None:
        super().__init__()
        self.agent_id = agent_id
        self.new_status = new_status


class InterruptReceived(Message):
    """An inter-agent interrupt / directive injection was received."""

    def __init__(self, message: InterAgentMessage) -> None:
        super().__init__()
        self.inter_agent_message = message


class SessionSelected(Message):
    """User selected a session from the picker."""

    def __init__(self, session_name: str) -> None:
        super().__init__()
        self.session_name = session_name


class NewSessionRequested(Message):
    """User requested creation of a new session."""

    def __init__(self, session_name: str, agent_count: int, goal: str) -> None:
        super().__init__()
        self.session_name = session_name
        self.agent_count = agent_count
        self.goal = goal
