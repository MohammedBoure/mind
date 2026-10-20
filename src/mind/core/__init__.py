"""Core terminal management and process multiplexing primitives."""

from mind.core.agent_discovery import discover_system_agents, get_agent_preset_config
from mind.core.pty_process import BasePtyProcess, spawn_pty
from mind.core.terminal_buffer import TerminalBuffer
from mind.core.terminal_manager import (
    AgentProfile,
    TerminalManager,
    WorkerProcessState,
    WorkerSession,
)

__all__ = [
    "AgentProfile",
    "BasePtyProcess",
    "TerminalBuffer",
    "TerminalManager",
    "WorkerProcessState",
    "WorkerSession",
    "discover_system_agents",
    "get_agent_preset_config",
    "spawn_pty",
]
