"""Domain models for the micro TUI state layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class AgentRole(Enum):
    """Role classification for an agent."""
    PRIMARY = "primary"
    WORKER = "worker"
    SUPERVISOR = "supervisor"


class AgentStatus(Enum):
    """Current operational status of an agent."""
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    WAITING = "waiting"
    ERROR = "error"


class MessagePriority(Enum):
    """Priority level for inter-agent messages."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AgentInfo:
    """Represents a single agent within a session."""
    id: int
    name: str
    role: AgentRole
    status: AgentStatus = AgentStatus.IDLE
    model: str = "gpt-4o"
    task: str = ""


@dataclass
class InterAgentMessage:
    """An inter-agent message / directive injection."""
    sender: str
    receiver: str
    priority: MessagePriority
    directive: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class SessionInfo:
    """Metadata for a session."""
    name: str
    created_at: datetime = field(default_factory=datetime.now)
    agent_count: int = 3
    goal: str = ""
    active: bool = True


@dataclass
class LogEntry:
    """A single log line in an agent's stream."""
    timestamp: datetime
    source: str
    content: str
    entry_type: str = "info"  # info, thought, tool_call, result, error
