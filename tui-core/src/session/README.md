# `tui-core/src/session/` — Multi-Agent Session, Identity Discovery & Shortcuts Engine

> **Swarm Session Orchestration, Real Identity Discovery & Configurable Shortcuts** for the compiled multi-agent TUI engine.
> Maintained by Systems & Backend Specialists (`agy11`).

---

## 1. Overview & Architecture

The `session` module provides complete session lifecycle management, persistence, dynamic agent slot discovery, and configurable keyboard shortcuts for the compiled TUI core.

```
+-----------------------------------------------------------------------------+
|                          Session & Identity Subsystem                       |
+-----------------------------------------------------------------------------+
|                               SessionManager                                |
|   ├── SessionStore: ~/.mind/sessions/<name>.json                            |
|   │     ├── SessionRecord ("default", "alpha_mission")                      |
|   │     ├── Activity Telemetry (steps, interactions, last_activity)         |
|   │     └── Atomic persistence & session pruning                            |
|   ├── IdentityDiscovery: ~/.local/share/agy-instances/agy[x]                 |
|   │     ├── Real Slot Metadata (slot_id: 11, role, model, task, token)      |
|   │     ├── GEMINI.md Role Parsing & settings.json Model Extraction         |
|   │     └── Environment Isolation (USERPROFILE, HOME, AGY_SLOT)             |
|   ├── ShortcutEngine: ~/.config/mind/agi.toml                               |
|   │     ├── Exact Python-Parity Shortcuts (q, ?, Tab, m, d, o, s, n)        |
|   │     └── Configurable Tab Keys (1..9, F5..F8) avoiding Alt conflicts     |
|   └── McpBackend implementation (JSON-RPC tool endpoints)                  |
+-----------------------------------------------------------------------------+
```

---

## 2. Files & Module Responsibilities

| File | Purpose |
|---|---|
| [`mod.rs`](file:///home/pluto/projects/mind/tui-core/src/session/mod.rs) | Public re-exports for session management, identity discovery, shortcuts, and persistent storage. |
| [`identity.rs`](file:///home/pluto/projects/mind/tui-core/src/session/identity.rs) | Host agent slot discovery engine (`IdentityDiscovery`, `AgentSlot`). Discovers slots under `~/.local/share/agy-instances/agy[x]`, inspects `.gemini/GEMINI.md` to extract real roles, reads `antigravity-cli/settings.json` for model configurations, extracts token/email metadata, and builds slot isolation environment variables. |
| [`session_store.rs`](file:///home/pluto/projects/mind/tui-core/src/session/session_store.rs) | Persistent session storage (`SessionStore`, `SessionRecord`, `SessionWorkerConfig`). Manages saving and loading multi-agent sessions to `~/.mind/sessions/<name>.json` with atomic rename writes, activity telemetry updates, and session pruning (`clean_sessions`). |
| [`shortcuts.rs`](file:///home/pluto/projects/mind/tui-core/src/session/shortcuts.rs) | Python-parity configurable shortcut engine (`ShortcutEngine`, `ShortcutConfig`, `AgiConfig`). Parses `~/.config/mind/agi.toml` and `~/.mind/config.toml`, resolves keyboard events into semantic `Action`s, and allows fully custom tab keys. |
| [`worker.rs`](file:///home/pluto/projects/mind/tui-core/src/session/worker.rs) | Worker session abstraction (`WorkerSession`) encapsulating PTY process, virtual screen buffer, state transitions (`Spawning`, `Running`, `Idle`, `Interrupted`, `Exited`), idle prompt heuristics (`is_idle_prompt`), role/model/task accessors, scrollback offset state (`scroll_offset`), and clean process termination (`kill`). |
| [`manager.rs`](file:///home/pluto/projects/mind/tui-core/src/session/manager.rs) | Central multi-agent orchestrator (`SessionManager`). Bridges active worker tabs with `SessionStore`, restores saved sessions, handles active tab focus cycling (`next_session`, `prev_session`, `select_index`), terminal resizing propagation (`broadcast_resize`), alarm queues, and graceful shutdown. |

---

## 3. Persistent Storage Specification (`~/.mind/sessions/<name>.json`)

Session records are serialized as structured JSON documents:

```json
{
  "name": "default",
  "created_at": "2026-10-23T20:00:00Z",
  "last_activity": "2026-10-23T22:30:00Z",
  "agent_count": 4,
  "goal": "Multi-Agent AI Orchestration & Parallel Systems Engineering",
  "active": true,
  "total_steps": 142,
  "total_interactions": 38,
  "status": "active",
  "working_dir": "/home/pluto/projects/mind",
  "workers": [
    {
      "id": "coordinator",
      "slot_id": "agy1",
      "role": "Lead Orchestrator",
      "model": "gemini-3.8-flash-high",
      "task": "Overseeing multi-agent fleet"
    },
    {
      "id": "worker-backend",
      "slot_id": "agy11",
      "role": "Backend Logic & Systems",
      "model": "gemini-3.8-flash-high",
      "task": "Core systems & API architecture"
    }
  ],
  "global_settings": {}
}
```

---

## 4. Host Slot Identity & Isolation (`IdentityDiscovery`)

Worker sessions are tied directly to host system slots under `/home/pluto/.local/share/agy-instances/agy[x]`:

- **Role Extraction**: Parsed from `# Role & Guidelines: <Role>` in `.gemini/GEMINI.md`, with automatic domain fallback based on slot ID ranges (e.g. 11..50 = Backend Logic & Systems, 51..100 = Frontend & UI/UX).
- **Model Detection**: Parsed from `model` in `.gemini/antigravity-cli/settings.json` (defaults to `gemini-3.8-flash-high`).
- **Slot Isolation**: Automatic generation of isolated environment variables:
  - `USERPROFILE`: `/home/pluto/.local/share/agy-instances/agy[x]`
  - `HOME`: `/home/pluto/.local/share/agy-instances/agy[x]`
  - `AGY_SLOT`: `x`
  - `AGY_INSTANCE_DIR`: `/home/pluto/.local/share/agy-instances/agy[x]`
  - `ANTIGRAVITY_APP_DATA_DIR`: `.../agy[x]/.gemini/antigravity-cli`
  - `MIND_REAL_USER_HOME`: `/home/pluto`

---

## 5. Python-Parity Configurable Shortcuts (`ShortcutEngine`)

The keyboard shortcut engine supports exact Python parity shortcuts and reads configurations from `~/.config/mind/agi.toml` (and `~/.mind/config.toml`):

| Key | Semantic Action | Description |
|---|---|---|
| `q` / `Ctrl+Q` | `Action::Quit` | Save session state and exit application |
| `?` | `Action::Help` | Toggle shortcuts help modal |
| `Tab` | `Action::CycleFocus` | Focus next worker tab / pane |
| `Shift+Tab` / `BackTab` | `Action::CycleFocusReverse` | Focus previous worker tab / pane |
| `m` / `Ctrl+M` | `Action::DirectiveModal` | Open Directive Injection Modal |
| `d` / `Ctrl+D` | `Action::DirectiveEditor` | Open In-app Directive Editor Modal |
| `o` / `Ctrl+O` | `Action::OpenExternalEditor` | Open directive file in system editor ($EDITOR) |
| `s` | `Action::ToggleSplit` | Toggle split layout (Single -> Horizontal -> Vertical -> Grid) |
| `n` | `Action::NewWorker` | Dynamically provision and spawn next agent slot |
| `1`..`9` / `F5`..`F8` | `Action::SelectTab(idx)` | Configurable fast tab jump keys |
| `PageUp` / `PageDown` | `Action::ScrollUp` / `Down` | Scroll terminal history buffer |
| `b` | UI Toggle | Toggle worker list and quota gauge sidebar |
| `F4` / `Alt+T` | Theme Toggle | Cycle themes (TokyoNight <-> HighContrastDark <-> HighContrastLight) |
| `Ctrl+C` | Interrupt | Send SIGINT to active worker process |

### Example `~/.config/mind/agi.toml`

```toml
[general]
theme = "tokyo_night"
tick_rate_ms = 50
default_session = "default"
default_model = "gemini-3.8-flash-high"

[shortcuts]
quit = ["q", "Ctrl+Q"]
help = ["?"]
cycle_focus = ["Tab"]
cycle_focus_reverse = ["Shift+Tab", "BackTab"]
directive_modal = ["m", "Ctrl+M"]
directive_editor = ["d", "Ctrl+D"]
open_external_editor = ["o", "Ctrl+O"]
toggle_split = ["s"]
new_worker = ["n"]
switch_tab_next = ["Tab", "F6"]
switch_tab_prev = ["Shift+Tab", "BackTab", "F5"]
tab_keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9"]
```

---

## 6. CLI Command Suite

```bash
# Enter active session or launch Session Picker
agi

# Create and immediately enter a new session
agi new my_mission

# Inspect saved sessions table
agi sessions

# Prune inactive / completed sessions
agi sessions --clean

# Run stdio MCP server for agent integration
agi --mcp-stdio

# Run performance benchmark suite
agi bench
```
