# `tui-core/src/session/` — Multi-Agent Session, Dual-Pane PTY Architecture & Vim Modal Engine

> **Dual-Pane PTY Swarm Architecture, Vim Modal State Machine, Real Identity Discovery & Storage Parity** for the compiled multi-agent TUI engine.
> Maintained by Systems & Backend Specialists (`agy11`).

---

## 1. Overview & Architecture

The `session` module provides complete 1:1 functional and architectural parity with Python `mind` for multi-agent session lifecycle management, dual-pane PTY multiplexing (Primary Coordinator on left, interactive Worker tabs on right), dual Vim modal states (`NORMAL` vs `PTY_INTERACT`), dynamic agent slot discovery, and two-way storage synchronization between individual sessions and `~/.mind/sessions.json`.

```
+---------------------------------------------------------------------------------------+
|                          Session & Dual-Pane Subsystem                                |
+---------------------------------------------------------------------------------------+
|                               SessionManager                                          |
|   ├── Dedicated Coordinator: Arc<WorkerSession> (#primary-pane / agy1)                |
|   ├── Ordered Workers: Vec<Arc<WorkerSession>> (#workers-pane / agy2..N)              |
|   ├── FocusedPane Tracking: FocusedPane::Coordinator vs FocusedPane::Workers(usize)   |
|   ├── Dual Vim-Style Mode State Machine:                                              |
|   │     ├── AppMode::Normal: Single-key commands (1..9, h/l, Tab, s, m, d, o, c, x, q) |
|   │     └── AppMode::PtyInteract: Raw keystroke passthrough to active PTY             |
|   │           └── Leader Exit: Ctrl+B, F12, or double-Escape (Esc Esc within 350ms)   |
|   ├── SessionStore: ~/.mind/sessions/<name>.json & ~/.mind/sessions.json              |
|   │     ├── SessionRecord with synchronized `workers` and `agent_configs`             |
|   │     ├── Activity Telemetry (steps, interactions, last_activity)                   |
|   │     └── Two-way JSON persistence & automatic pruning                              |
|   ├── IdentityDiscovery: ~/.local/share/agy-instances/agy[x]                           |
|   │     ├── Real Slot Metadata (slot_id: 11, role, model, task, token, email)         |
|   │     ├── GEMINI.md Role Parsing & settings.json Model Extraction                   |
|   │     └── Environment Isolation (USERPROFILE, HOME, AGY_SLOT, AGY_INSTANCE_DIR)     |
|   ├── ShortcutEngine: ~/.config/mind/agi.toml                                         |
|   │     └── Configurable key mapping with Python-parity fallback defaults             |
|   └── McpBackend implementation (Stdio JSON-RPC 2.0 tool endpoints)                   |
+---------------------------------------------------------------------------------------+
```

---

## 2. Files & Module Responsibilities

| File | Purpose |
|---|---|
| [`mod.rs`](file:///home/pluto/projects/mind/tui-core/src/session/mod.rs) | Public re-exports for session management, dual-pane types (`FocusedPane`, `AppMode`), identity discovery, shortcuts, and persistent storage. |
| [`manager.rs`](file:///home/pluto/projects/mind/tui-core/src/session/manager.rs) | Central multi-agent orchestrator (`SessionManager`). Holds dedicated `coordinator` and ordered `workers`, tracks `FocusedPane`, executes Vim mode transitions (`enter_pty`, `enter_normal`), handles `Tab` pane focus toggling, worker tab jumping (`jump_worker_tab`), cycling (`next_worker_tab`, `prev_worker_tab`), worker closing (`close_active_worker`), terminal resize propagation (`broadcast_resize`), and MCP tools. |
| [`session_store.rs`](file:///home/pluto/projects/mind/tui-core/src/session/session_store.rs) | Persistent session storage (`SessionStore`, `SessionRecord`, `SessionWorkerConfig`). Manages saving and loading multi-agent sessions to both `~/.mind/sessions/<name>.json` and aggregate `~/.mind/sessions.json` with two-way field synchronization (`sync_configs`), atomic rename writes, activity telemetry updates, and session pruning (`clean_sessions`). |
| [`shortcuts.rs`](file:///home/pluto/projects/mind/tui-core/src/session/shortcuts.rs) | Python-parity configurable shortcut engine (`ShortcutEngine`, `ShortcutConfig`, `AgiConfig`). Parses `~/.config/mind/agi.toml` and `~/.mind/config.toml`, resolves keyboard events into semantic `Action`s, and allows fully custom tab keys. |
| [`worker.rs`](file:///home/pluto/projects/mind/tui-core/src/session/worker.rs) | Worker session abstraction (`WorkerSession`) encapsulating PTY process, virtual screen buffer, state transitions (`Spawning`, `Running`, `Idle`, `Interrupted`, `Exited`), idle prompt heuristics (`is_idle_prompt`), role/model/task accessors, scrollback offset state (`scroll_offset`), and clean process termination (`kill`). |
| [`identity.rs`](file:///home/pluto/projects/mind/tui-core/src/session/identity.rs) | Host agent slot discovery engine (`IdentityDiscovery`, `AgentSlot`). Discovers slots under `~/.local/share/agy-instances/agy[x]`, inspects `.gemini/GEMINI.md` to extract real roles, reads `antigravity-cli/settings.json` for model configurations, extracts token/email metadata, and builds slot isolation environment variables. |

---

## 3. Dual-Pane PTY Architecture & Focus Tracking

To match Python `mind` (`workspace.py`), the workspace layout separates the terminal into two primary panes:
- **Left Pane (`#primary-pane`)**: Dedicated Primary Coordinator running slot 1 (`agy1`). This terminal acts as the lead orchestrator and stays visible on screen at all times.
- **Right Pane (`#workers-pane`)**: Interactive Worker Multiplexer with a visible tab bar at top (`1..9`) and the active worker terminal below.

### Focus Navigation & Keystrokes
- `FocusedPane::Coordinator`: Focus is directed to the left Primary Coordinator PTY.
- `FocusedPane::Workers(usize)`: Focus is directed to worker tab `usize` on the right pane.
- **`Tab` / `Shift+Tab`**: Toggles focus back and forth between `FocusedPane::Coordinator` and the active worker tab via `switch_pane_focus()`.
- **`1`..`9`**: Jumps directly to worker tab #1 through #9 via `jump_worker_tab(n)`.
- **`h` / `l`**: Cycles worker tabs left or right in the workers pane via `prev_worker_tab()` and `next_worker_tab()`.

---

## 4. Dual Vim-Style Mode State Machine

`SessionManager` exposes `AppMode` with two distinct operational states matching Python `mind`:

### 1. `AppMode::Normal` (Command Mode)
Single keys trigger application management actions without leaking to child processes:
- `i`, `Enter`, or `a`: Enters `AppMode::PtyInteract`.
- `1`..`9`: Jump to worker tab N.
- `h` / `l`: Previous / Next worker tab.
- `Tab` / `Shift+Tab`: Switch focus between Coordinator and Worker pane.
- `s`: Toggle between 50/50 dual split and full-screen focused pane.
- `m`: Open directive injection modal.
- `d`: Open in-app multiline directive editor modal.
- `o`: Open active agent's directive file in external `$EDITOR`.
- `c` / `n`: Open new worker modal or spawn new agent slot.
- `x`: Terminate and close active worker tab (`close_active_worker()`).
- `?`: Open shortcuts help modal.
- `q`: Clean shutdown and exit.
- `y`: Yank / copy focused terminal buffer to system clipboard.

### 2. `AppMode::PtyInteract` (Insert Mode)
All keystrokes (alphanumerics, enter, backspace, arrows, Ctrl+C) are piped raw directly into the focused child PTY.

Exiting back to `Normal` mode is governed by explicit Leader keys:
- **`Ctrl+B`**: Immediate switch back to `AppMode::Normal`.
- **`F12`**: Immediate switch back to `AppMode::Normal`.
- **Double-Escape (`Esc Esc` within 350ms)**: Switches back to `AppMode::Normal`. If `Esc` is pressed only once, the byte `\x1b` is forwarded cleanly to the child PTY.

---

## 5. Storage Parity & Synchronization

`SessionStore` guarantees 1:1 two-way compatibility between compiled Rust `agi` and Python `mind`:
- **Individual Session Files**: `~/.mind/sessions/<name>.json`.
- **Aggregate Sessions File**: `~/.mind/sessions.json`.
- **Automatic Field Synchronization (`sync_configs`)**:
  - Automatically bridges Rust's `workers: Vec<SessionWorkerConfig>` and Python's `agent_configs: dict[str, dict[str, Any]]`.
  - Preserves metrics (`total_steps`, `total_interactions`, `last_activity`, `status`).
  - Merges records across both storage formats when listing sessions.

---

## 6. Auto-Spawning Real `agy` CLI & Slot Environment Isolation

`SessionManager` and `WorkerSession` natively support automatically launching the real Google Antigravity (`agy`) CLI inside PTY terminals for both the Primary Coordinator and interactive Worker tabs, with full filesystem and identity isolation per agent slot.

### A. Detection Flow for `agy` Binary (`find_agy_binary`)
The engine discovers the executable binary through priority-ordered paths:
1. `/home/pluto/.local/bin/agy` (and real host user's `~/.local/bin/agy`).
2. `/usr/local/bin/agy`.
3. `/usr/bin/agy`.
4. PATH environment resolution via `which agy` (POSIX) or `where agy` (Windows).
5. Instance slot fallback under `~/.local/share/agy-instances/agy11/bin/agy`.
6. Verified executable permissions check (`mode & 0o111 != 0`).

### B. Coordinator Isolated Environment (Slot 1 / `#primary-pane`)
When spawning or restoring the Primary Coordinator:
- Automatically launches `agy` with Coordinator environment:
  - `USERPROFILE`: `/home/pluto/.local/share/agy-instances/agy1`
  - `HOME`: `/home/pluto/.local/share/agy-instances/agy1`
  - `AGY_SLOT`: `1`
  - `AGY_INSTANCE_DIR`: `/home/pluto/.local/share/agy-instances/agy1`
  - `ANTIGRAVITY_APP_DATA_DIR`: `/home/pluto/.local/share/agy-instances/agy1/.gemini/antigravity-cli`
  - `MIND_REAL_USER_HOME`: `/home/pluto`
- Falls back cleanly to system shell (`bash` or `powershell.exe`) only if `agy` binary is not executable.

### C. Worker Isolated Environments (Slot [x] / `#workers-pane`)
When spawning or restoring interactive worker slots (e.g. `agy11`, `agy51`, `agy100`):
- Automatically launches `agy` with the specific worker's isolated slot environment:
  - `USERPROFILE`: `/home/pluto/.local/share/agy-instances/agy[x]`
  - `HOME`: `/home/pluto/.local/share/agy-instances/agy[x]`
  - `AGY_SLOT`: `[x]`
  - `AGY_INSTANCE_DIR`: `/home/pluto/.local/share/agy-instances/agy[x]`
  - `ANTIGRAVITY_APP_DATA_DIR`: `/home/pluto/.local/share/agy-instances/agy[x]/.gemini/antigravity-cli`
  - `MIND_REAL_USER_HOME`: `/home/pluto`

### D. Configuration Option in `~/.config/mind/agi.toml`
Controlled via the `[general]` configuration section:
```toml
[general]
theme = "tokyo_night"
tick_rate_ms = 50
default_model = "gemini-3.8-flash-high"
auto_spawn_agy = true  # (default: true). If false, spawns user default shell.
```
- When `auto_spawn_agy = true`: Spawns the detected `agy` CLI in all coordinator and worker PTYs.
- When `auto_spawn_agy = false`: Spawns the user's default shell (`bash` or `powershell.exe`).

---

## 7. Environment & Configuration

- Configuration files searched: `~/.config/mind/agi.toml` and `~/.mind/config.toml`.
- Persistent session directory: `~/.mind/sessions/` and `~/.mind/sessions.json`.
- Agent instance directory: `~/.local/share/agy-instances/agy[x]`.
