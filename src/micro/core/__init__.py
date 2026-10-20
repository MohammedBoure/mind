"""Core terminal management and process multiplexing primitives."""

from micro.core.pty_process import BasePtyProcess, spawn_pty
from micro.core.terminal_buffer import TerminalBuffer
from micro.core.terminal_manager import (
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
    "spawn_pty",
]
