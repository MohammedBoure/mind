"""Core terminal management and process multiplexing primitives."""

from mind.core.agent_discovery import discover_system_agents, get_agent_preset_config
from mind.core.credentials import (
    CrossProcessCredentialLock,
    extract_email_from_token,
    get_slot_token_path,
    read_credential,
    restore_slot_credential,
    setup_slot_env,
    write_credential,
)
from mind.core.pty_process import (
    BasePtyProcess,
    WindowsInputSanitizer,
    reap_process_tree,
    spawn_pty,
)
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
    "CrossProcessCredentialLock",
    "TerminalBuffer",
    "TerminalManager",
    "WindowsInputSanitizer",
    "WorkerProcessState",
    "WorkerSession",
    "discover_system_agents",
    "extract_email_from_token",
    "get_agent_preset_config",
    "get_slot_token_path",
    "read_credential",
    "reap_process_tree",
    "restore_slot_credential",
    "setup_slot_env",
    "spawn_pty",
    "write_credential",
]
