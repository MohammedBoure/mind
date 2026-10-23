# `tui-core/src/session/` — Multi-Agent Session & Process Manager

This directory manages worker and coordinator agent session lifecycles, active tab switching, terminal geometry synchronization, and MCP tool execution.

## Files

| File | Purpose |
|---|---|
| `mod.rs` | Public re-exports for session management (`SessionManager`, `WorkerSession`, `WorkerState`). |
| `worker.rs` | Worker session abstraction (`WorkerSession`) encapsulating PTY process, virtual screen buffer, state transitions (`Spawning`, `Running`, `Idle`, `Interrupted`, `Exited`), idle prompt heuristics (`is_idle_prompt`), and metadata summary reporting. |
| `manager.rs` | Central multi-agent orchestrator (`SessionManager`). Manages ordered worker tabs, active tab focus cycling (`next_session`, `prev_session`, `select_index`), terminal resizing propagation (`broadcast_resize`), alarm queues, and implements the `McpBackend` trait to power MCP tools. |
