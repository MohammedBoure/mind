# UI Widgets, Modals & Visual Screens (`tui-core/src/ui`)

> **Frontend & Interface Auditor Specification** for the compiled multi-agent TUI engine.
> Maintained by Frontend & UI/UX Engineer (`agy51`) using Rust, Ratatui 0.29, and Crossterm 0.28.
> **1:1 Pixel-Perfect Visual Parity with Python `mind` (Textual `WorkspaceScreen`, `HeaderBar`, `BottomBar`, and Modals).**

---

## 1. Overview & Architecture

The `ui` module provides a comprehensive suite of reactive, accessible visual widgets, modal popups, and full-screen pickers engineered for low-latency terminal multiplexing across dozens of concurrent AI agent worker terminals (`agy1` .. `agyN`).

The module completely decouples backend PTY process buffers, identity discovery, and MCP events from Ratatui presentation, achieving exact 1:1 visual parity with Python `mind`:
- **Dual-Pane Workspace Layout (`WorkspaceScreen`)**:
  - **Left Pane (`#primary-pane`)**: Dedicated Primary Coordinator PTY (Slot 1 `agy1`). Stays visible side-by-side.
  - **Right Pane (`#workers-pane`)**: Worker Multiplexer with top `WorkerTabBar` (tabs `1..9`) and active worker PTY viewport below.
  - **Focus Visuals**: Active pane gets prominent Tokyo Night accent border (`#7aa2f7` / `#7dcfff`); inactive pane has muted border (`#565f89` / `#7982a9`).
  - **Split Layout Modes**: Side-by-side (50/50) vs Fullscreen expansion toggle on `s` key (Coordinator 100% or Workers 100%).
- **Zellij-Style Top HeaderBar (`HeaderBar`)**:
  - 1-line dock-top layout:
    - **Brand Logo**: `mind` (bold cyan `#7aa2f7`)
    - **Session Name**: active session in `#7dcfff` on `#24283b`
    - **Quota Pill**: `[████████░░]` progress bar + percentage / remaining steps in Tokyo Night Green `#9ece6a`
    - **MCP Status**: `● MCP: 8765` (green dot `#9ece6a`)
    - **Worker Telemetry**: `X active workers` in Warm Gold `#e0af68`
- **Multi-Segment BottomBar (`BottomBar`)**:
  - 1-line dock-bottom layout:
    - **Mode Indicator**: `[ NORMAL MODE ]` (bold on `#e0af68`) vs `[ PTY INTERACT ]` (bold on `#7aa2f7`)
    - **Action Pills**: `[?] Help`, `[m] Directive`, `[s] Split`, `[d] Edit`, `[c/n] New`, `[x] Close`, `[q] Quit` (Normal mode) and `[Esc Esc / Ctrl+B] Outer Normal`, `[Ctrl+C] Interrupt` (PTY mode)
    - **Arch Badge**: `POSIX PTY · UTF-8` / `ConPTY · UTF-8` on far right
- **Modals Matching Python `mind`**:
  - **`HelpModal`**: Clean popup with keybindings, leader exit (`Esc Esc`, `Ctrl+B`, `F12`), Normal mode shortcuts.
  - **`DirectiveModal`**: Priority selector (High, Medium, Low, Critical) with color highlights and directive text input.
  - **`DirectiveEditorModal`**: Multiline directive editor with line numbers (`1 │ `, `2 │ `...) and `Ctrl+S` persistence.
  - **`SelectWorkerModal`**: Slot selector list (`agy1..200`) with live search filter, role titles, and token status.
  - **`SessionPickerScreen`**: Formatted session list table (`Session Name`, `Agents`, `Status`, `Steps`, `Tasks`, `Last Active`, `Goal`).

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ mind  session_1  [NORMAL]                       4 active workers  Quota: [████████░░] 80%  ● MCP: 8765 │ <- HeaderBar
├────────────────────────────────────────────────────┬───────────────────────────────────────────────────┤
│ 👑 Primary Coordinator (Slot 1 agy1) [FOCUSED]     │ Interactive Workers [1..9 / h / l]                │
│                                                    │  ▶1: Worker-1 (agy11)   2: Worker-2 (agy51)  +New │ <- WorkerTabBar
│                                                    ├───────────────────────────────────────────────────┤
│ Active Coordinator PTY Terminal Viewport           │ Active Worker PTY Terminal Viewport               │
│ (ansi virtual screen matrix, zero-overhead dirty   │ (raw terminal IO pass-through, scrollback history,│
│  frame caching, prominent #7aa2f7 accent border)   │  insert cursor, #7dcfff tab highlight)            │
│                                                    │                                                   │
├────────────────────────────────────────────────────┴───────────────────────────────────────────────────┤
│ [ NORMAL MODE ] [?] Help  [m] Directive  [s] Split  [d] Edit  [c/n] New  [x] Close   POSIX PTY · UTF-8 │ <- BottomBar
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
│ Overlays: Centered Ratatui Modals (Clear backdrop)                                                     │
│ ├── HelpModal: Keybindings, leader exit (Esc Esc, Ctrl+B, F12), Normal mode shortcuts                  │
│ ├── DirectiveModal: Priority selector (High, Medium, Low) and prompt input                            │
│ ├── DirectiveEditorModal: Multiline directive editor with line numbers                                 │
│ ├── SelectWorkerModal: Slot selector list (agy1..200) with search filter                               │
│ └── SessionPickerScreen: Formatted session list table                                                  │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Itemized File Breakdown & Responsibilities

| File | Module | Responsibility |
|---|---|---|
| [`mod.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/mod.rs) | `ui` | Public module exports, widget facade, modal action types, and theme re-exports. |
| [`workspace.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/workspace.rs) | `ui::workspace` | Dual-pane workspace screen (`WorkspaceScreen`) and worker multiplexer tab bar (`WorkerTabBar`). Implements 50/50 side-by-side vs fullscreen layout modes and Tokyo Night active focus borders. |
| [`header_bar.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/header_bar.rs) | `ui::header_bar` | Zellij-inspired top HeaderBar widget displaying bold cyan `mind` logo, active session pill, quota progress bar, green dot MCP health status, and worker count telemetry. |
| [`bottom_bar.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/bottom_bar.rs) | `ui::bottom_bar` | Multi-segment BottomBar widget displaying mode indicator badge (`NORMAL MODE` vs `PTY INTERACT`), dynamic action pills, notice alerts, and platform architecture badge (`POSIX PTY` / `ConPTY`). |
| [`select_worker_modal.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/select_worker_modal.rs) | `ui::select_worker_modal` | Slot selector modal (`SelectWorkerModal`) with live search filter query, table columns (slot, role, model, status, email), and spawn action. |
| [`new_worker_modal.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/new_worker_modal.rs) | `ui::new_worker_modal` | Backward-compatibility facade re-exporting `SelectWorkerModal` as `NewWorkerModal`. |
| [`agent_config_modal.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/agent_config_modal.rs) | `ui::agent_config_modal` | In-app agent settings modal (`AgentConfigModal`, `e` in Normal mode / `Ctrl+E` in PTY mode). Allows interactive navigation across all active tabs (`Coordinator`, `Worker-1`..), live cycling of assigned host agy slots (`agy1`..`agy200`), and instant persistence or live restart (`Ctrl+R`). |
| [`help_modal.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/help_modal.rs) | `ui::help_modal` | Accessible shortcuts help popup modal (`HelpModal`) matching Python Mind: Vim modal architecture, leader exits (`Esc Esc`, `Ctrl+B`, `F12`), Normal mode single-key shortcuts, directives, and clipboard. |
| [`directive_modal.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/directive_modal.rs) | `ui::directive_modal` | Directive injection modal (`DirectiveModal`), priority selection (`DirectivePriority`: Low, Normal, High, Critical), text cursor input, and submit action. |
| [`directive_editor.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/directive_editor.rs) | `ui::directive_editor` | In-app multiline directive editor modal (`DirectiveEditorModal`) with line numbers gutter (`1 │ `), scrolling, cursor positioning, and `Ctrl+S` persistence. |
| [`session_picker.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/session_picker.rs) | `ui::session_picker` | Interactive full-screen session picker (`SessionPickerScreen`), table listing, inline new session prompt dialog, deletion confirmation, and `SessionPickerAction`. |
| [`split_panes.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/split_panes.rs) | `ui::split_panes` | Multiplexer widget supporting Single, Horizontal, Vertical, and Grid layouts with active focus borders and history scroll indicators. |
| [`status_bar.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/status_bar.rs) | `ui::status_bar` | Accessible status bar displaying active worker ID, real slot ID, role title, PID, model, token counters, and alert badges. |
| [`worker_list.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/worker_list.rs) | `ui::worker_list` | Dynamic worker session list widget with real role titles, process states (`●`, `○`, `⚡`, `🚨`), task previews, and selection indicators. |
| [`gauges.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/gauges.rs) | `ui::gauges` | Real-time progress gauges for hourly quota, weekly quota, and CPU/RAM usage meters with theme-aware color thresholds. |
| [`terminal_screen.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/terminal_screen.rs) | `ui::terminal_screen` | Zero-overhead ANSI character matrix renderer supporting both live cell buffers and history scrollback slices (`from_owned_cells`). |
| [`theme.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/theme.rs) | `ui::theme` | Color palette tokens, accessible theme modes (Tokyo Night, High Contrast Dark/Light, Color-Blind), glyphs, and style helpers. |

---

## 3. Component Specifications & State Models

### 3.1 WorkspaceScreen & WorkerTabBar (`workspace.rs`)
- **State Model**:
  ```rust
  pub struct WorkspaceScreen {
      pub is_split_view: bool,
      pub focused_pane: FocusedPane,
      pub mode: AppMode,
      pub coordinator: Option<Arc<WorkerSession>>,
      pub workers: Vec<Arc<WorkerSession>>,
      pub theme: Theme,
  }
  ```
- **Geometry & Layout Calculation**:
  - `is_split_view == true`: 50/50 side-by-side split. Left coordinator pane takes 50% width; right worker multiplexer pane takes 50% width.
  - `is_split_view == false`: Fullscreen toggle on `s` key. If Coordinator is focused, Left pane expands to 100% width. If Worker is focused, Right pane expands to 100% width.
- **Visual Styling**:
  - Focused pane: prominent Tokyo Night accent border (`#7aa2f7` / `#7dcfff`, bold).
  - Inactive pane: muted border (`#565f89`).

### 3.2 HeaderBar (`header_bar.rs`)
- **State Model**:
  ```rust
  pub struct HeaderBar {
      pub session_name: String,
      pub worker_count: usize,
      pub mode: AppMode,
      pub quota_percent: u8,
      pub quota_text_override: Option<String>,
      pub mcp_port: u16,
      pub mcp_active: bool,
      pub theme: Theme,
  }
  ```
- **Visual Pattern**:
  - Background: Tokyo Night Night `#16161e`.
  - Brand Logo: `mind` in bold cyan `#7aa2f7`.
  - Session Name: active session in `#7dcfff` on `#24283b`.
  - Quota Pill: `[████████░░] 80%` in bold green `#9ece6a` on `#1f2335`.
  - MCP Status: `● MCP: 8765` with active green dot `#9ece6a`.

### 3.3 BottomBar (`bottom_bar.rs`)
- **State Model**:
  ```rust
  pub struct BottomBar {
      pub mode: AppMode,
      pub active_notice: Option<String>,
      pub pty_backend: String,
      pub theme: Theme,
  }
  ```
- **Action Pills**:
  - Normal Mode: `[?] Help`, `[m] Directive`, `[s] Split`, `[d] Edit`, `[c/n] New`, `[x] Close`, `[q] Quit`, `[i] Type`, `[1..9] Jump`, `[h/l] Tabs`, `[y] Copy`.
  - PTY Interact Mode: `[Esc Esc / Ctrl+B] Outer Normal`, `[Ctrl+C] Interrupt`, `[Ctrl+M] Inject`, `[Ctrl+D] Directive`, `[Ctrl+Shift+C] Copy`, `[?] Help`.
  - Architecture Badge: `POSIX PTY · UTF-8` on Linux/macOS, `ConPTY · UTF-8` on Windows.

### 3.4 SelectWorkerModal (`select_worker_modal.rs`)
- **State Model**:
  ```rust
  pub struct SelectWorkerModal {
      pub slots: Vec<AgentSlot>,
      pub filter_query: String,
      pub selected_index: usize,
      pub is_open: bool,
      pub theme: Theme,
  }
  ```
- **Features**:
  - Live search filter input box: filters slots dynamically across slot ID (`agy1`..`200`), name, role, model, and email.
  - Up/Down navigation with clamping.
  - Spawns selected slot on `Enter`, cancels on `Esc`.

### 3.5 HelpModal (`help_modal.rs`)
- **State Model**:
  ```rust
  pub struct HelpModal {
      theme: Theme,
      is_open: bool,
  }
  ```
- **Features**:
  - Categorized reference cards: Vim-like Modal Architecture, Mode Switching & Leader Controls (`Esc Esc`, `Ctrl+B`, `F12`), Normal Mode Navigation & Tab Controls (`1..9`, `h/l`, `c`, `x`, `s`, `Tab`), Inter-Agent & Directive Injection (`m`, `d`, `o`, `Ctrl+C`), and Clipboard.

---

## 4. Keyboard Shortcuts & Leader Key Controls

| Hotkey / Shortcut | Mode | Action |
|---|---|---|
| `i` / `Enter` / `a` | Normal | Enter PTY Insert mode (stream raw keystrokes to child process) |
| `Esc Esc` (double-tap <350ms) | PTY | Exit PTY mode and return to Normal mode |
| `Ctrl+B` | PTY | Exit PTY mode and return to Normal mode (leader key 1) |
| `F12` | PTY | Exit PTY mode and return to Normal mode (leader key 2) |
| `Tab` | Normal | Toggle focus between Primary Coordinator (`#primary-pane`) and Worker Multiplexer (`#workers-pane`) |
| `s` | Normal | Toggle split layout: Side-by-side (50/50) vs Fullscreen focused pane |
| `1`..`9` | Normal | Jump directly to Worker tab #1..#9 |
| `h` / `l` | Normal | Switch to previous / next worker tab |
| `c` / `n` | Normal | Open `SelectWorkerModal` to provision/spawn new worker slot |
| `x` | Normal | Terminate and close active worker tab |
| `m` / `Ctrl+M` | Any | Open `DirectiveModal` to inject prioritized task prompt |
| `d` / `Ctrl+D` | Any | Open `DirectiveEditorModal` in-app multiline editor |
| `o` / `Ctrl+O` | Any | Open directive file in external editor (`$EDITOR`) |
| `Ctrl+C` | Any | Send SIGINT interrupt to active worker PTY |
| `Ctrl+P` | Normal | Launch interactive `SessionPickerScreen` |
| `?` | Normal | Toggle `HelpModal` keyboard shortcuts reference |
| `q` | Normal | Cleanly shut down worker processes, persist session, and quit |

---

## 5. Testing & Verification

The UI test suite passes 100% across unit and integration tests:
- `ui::header_bar::tests`: Verifies logo branding, session name, quota progress bar, and MCP indicator rendering.
- `ui::bottom_bar::tests`: Verifies normal mode action pills, PTY mode action pills, and architecture badge.
- `ui::workspace::tests`: Verifies dual-pane geometry, 50/50 split vs fullscreen toggle on `s`, and `WorkerTabBar` rendering.
- `ui::select_worker_modal::tests`: Verifies live search query filtering, slot navigation, and spawn dispatch.
- `ui::help_modal::tests`: Verifies modal open/close transitions, leader keys, and hotkey reference rendering.
- `tests/ui_widgets_test.rs`: 18 comprehensive integration tests covering all widgets and modals.

Run the test suite:
```bash
cargo test --manifest-path tui-core/Cargo.toml
```
