# `tui-core/src/session/` — Multi-Agent Session & Process Manager

> **Swarm Session Orchestration & Ergonomics** for the compiled multi-agent TUI engine.
> Maintained by Systems & UX Polish Specialists.

---

## 1. Overview & Architecture

The `session` module orchestrates all managed worker agent sessions (`WorkerSession`), handles keyboard tab switching (`Tab`, `Shift+Tab`, `Alt+1`..`Alt+9`), coordinates PTY terminal dimensions across the swarm, manages per-session scrollback offsets, and provides the backend data layer for Model Context Protocol (MCP) tool queries.

```
+-----------------------------------------------------------------------------+
|                          SessionManager Orchestrator                        |
+-----------------------------------------------------------------------------+
|                               SessionManager                                |
|   ├── sessions: Vec<Arc<WorkerSession>>                                     |
|   │     ├── [0] "coordinator" (agy1)                                        |
|   │     ├── [1] "worker-build" (agy2)                                       |
|   │     └── [2] "worker-bench" (agy3)                                       |
|   ├── active_index: usize (Focused Tab receiving keyboard input)            |
|   ├── alarms: Vec<AlarmEvent> (Coordinator event queue)                     |
|   └── McpBackend implementation (JSON-RPC tool endpoints)                  |
+-----------------------------------------------------------------------------+
```

---

## 2. Files & Module Responsibilities

| File | Purpose |
|---|---|
| [`mod.rs`](file:///home/pluto/projects/mind/tui-core/src/session/mod.rs) | Public re-exports for session management (`SessionManager`, `WorkerSession`, `WorkerState`). |
| [`worker.rs`](file:///home/pluto/projects/mind/tui-core/src/session/worker.rs) | Worker session abstraction (`WorkerSession`) encapsulating PTY process, virtual screen buffer, state transitions (`Spawning`, `Running`, `Idle`, `Interrupted`, `Exited`), idle prompt heuristics (`is_idle_prompt`), scrollback offset state (`scroll_offset`), and clean process termination (`kill`). |
| [`manager.rs`](file:///home/pluto/projects/mind/tui-core/src/session/manager.rs) | Central multi-agent orchestrator (`SessionManager`). Manages ordered worker tabs, active tab focus cycling (`next_session`, `prev_session`, `select_index`), terminal resizing propagation (`broadcast_resize`), alarm queues, graceful swarm shutdown (`shutdown_all`), and implements the `McpBackend` trait. |

---

## 3. Ergonomic Navigation & Tab Controls

1. **Sequential Tab Cycling**:
   - `next_session()`: Cycles focus to the next tab (`(active_index + 1) % len`). Bound to `Tab`.
   - `prev_session()`: Cycles focus to the previous tab (`(active_index - 1 + len) % len`). Bound to `Shift+Tab` / `BackTab`.

2. **Direct Tab Jumping**:
   - `select_index(target_index)`: Directly jumps to tab `target_index` if within bounds. Bound to `Alt+1` through `Alt+9`.

3. **Per-Session Scrollback Navigation**:
   - Each `WorkerSession` maintains its own independent `scroll_offset: Arc<Mutex<usize>>`.
   - `scroll_up(delta)`: Increases scroll offset up to the total lines in history (`history_count()`). Bound to `PageUp` / `Shift+Up`.
   - `scroll_down(delta)`: Decreases scroll offset toward 0. Bound to `PageDown` / `Shift+Down`.
   - `reset_scroll()`: Resets scroll offset to 0 (live view at bottom). Automatically triggered on any user input delivery (`send_input`).

4. **Graceful Swarm Shutdown**:
   - `shutdown_all()`: Iterates over all active sessions and invokes `session.kill()`, terminating child PTY processes and preventing orphan/zombie processes upon application exit (`Ctrl+Q`).
