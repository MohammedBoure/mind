# UI Widgets, Modals & Visual Screens (`tui-core/src/ui`)

> **Frontend & Interface Auditor Specification** for the compiled multi-agent TUI engine.
> Maintained by Frontend & UI/UX Engineer (`agy51`) using Rust, Ratatui 0.29, and Crossterm 0.28.

---

## 1. Overview & Architecture

The `ui` module provides a comprehensive suite of reusable, reactive, accessible visual widgets, modal popups, and full-screen pickers engineered for low-latency terminal multiplexing across dozens of concurrent AI agent worker terminals (`agy1` .. `agyN`).

The module completely decouples backend PTY process buffers, identity discovery, and MCP events from Ratatui presentation, providing:
- **Interactive Session Picker Screen**: Full-screen table listing persistent sessions with inline session creation, deletion, activity telemetry, and fast loading.
- **Python-Parity Modals**:
  - **Shortcuts Help Modal** (`?`): Accessible categorized hotkey reference card matching `agi.toml` and Python mind shortcuts.
  - **Directive Injection Modal** (`m` / `Ctrl+M`): Prioritized directive messaging (Low, Normal, High, Critical) with asynchronous MCP injection.
  - **In-App Directive Editor Modal** (`d` / `Ctrl+D`): Multiline text editor widget with line numbering, cursor navigation, and Ctrl+S persistence.
  - **New Worker Modal** (`n`): Host agent slot discovery (`IdentityDiscovery`), table of slot metadata (role, model, token status), and isolated environment provisioning.
- **Real Agent Identity & Role Indicators**: Integrated slot IDs (`agy[x]`), human-friendly worker names, and real role titles extracted dynamically from `.gemini/GEMINI.md` and workspace assignments.
- **Dirty-Frame Caching**: $O(1)$ integer version comparisons (12.18 ns) eliminate redundant re-rendering when screen buffers have not mutated.
- **Accessible Theme Palettes**: Runtime theme cycling across Tokyo Night, High Contrast Dark (WCAG AAA), High Contrast Light, and Color-Blind Universal Design (Protanopia / Deuteranopia safe).
- **Responsive Split Multiplexing**: Single pane, horizontal split, vertical split, and 2x2 quad grid with active focus highlighting.
- **Scrollback History Exploration**: Per-session scrolling offset (`PageUp`/`PageDown`) with instant scroll position indicator badges (`[SCROLL -N]`).

```
+-----------------------------------------------------------------------------------+
|                         tui-core Visual UI Hierarchy                              |
+-----------------------------------------------------------------------------------+
| Top Header: Tabs [ ▶ 1:agy11 [Backend] | 2:agy51 [Frontend] [Alt+2] ]             |
|             Session: AGI Session: default                                         |
+-----------------------------------+-----------------------------------------------+
| Left Sidebar (b toggle):          | Main Area: SplitPanesWidget                   |
| ├── WorkerListWidget              | ├── SplitMode::Single (1-Pane)                |
| │   ├── ● 1:agy11 [Backend Logic] | ├── SplitMode::Horizontal (Side-by-side)      |
| │   ├── ● 2:agy51 [Frontend UI/UX]| ├── SplitMode::Vertical (Stacked)             |
| │   └── ⚡ 3:agy100 [Testing Gate] | └── SplitMode::Grid (2x2 Quad Panes)          |
| └── QuotaGaugesWidget (Horizontal)|                                               |
|     (Hourly, Weekly, CPU, RAM)    | TerminalScreenWidget: ANSI ScreenCell Matrix  |
|                                   | with scrollback history support [SCROLL -N]   |
+-----------------------------------+-----------------------------------------------+
| Bottom: StatusBarWidget (Accessible Theme Mode)                                   |
| [ ● 1:agy11 [Backend Logic] ] [ PID: 1234 ] [ gemini-3.8-flash ] [ Tokens: 18.5k ]|
| [ ⚡ Worker Finished / 🚨 Assistance Needed ] [ [SPLIT: HORIZ] ] [ Hotkeys Guide ]|
+-----------------------------------------------------------------------------------+
| Overlays: Centered Ratatui Modals (Clear backdrop)                                |
| ├── SessionPickerScreen: Full-screen table of saved sessions (`Ctrl+P` / `agi picker`)|
| ├── HelpModal: Hotkey reference card (`?`)                                        |
| ├── DirectiveModal: Directive Injection with priority selector (`m` / `Ctrl+M`)   |
| ├── DirectiveEditorModal: In-app multiline editor (`d` / `Ctrl+D`)                |
| └── NewWorkerModal: Host slot provisioner (`n`)                                   |
+-----------------------------------------------------------------------------------+
```

---

## 2. Itemized File Breakdown & Responsibilities

| File | Module | Responsibility |
|---|---|---|
| [`mod.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/mod.rs) | `ui` | Public module exports, widget facade, modal action types, and theme re-exports. |
| [`session_picker.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/session_picker.rs) | `ui::session_picker` | Interactive full-screen session picker (`SessionPickerScreen`), table listing, inline new session prompt dialog, deletion confirmation, and `SessionPickerAction`. |
| [`help_modal.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/help_modal.rs) | `ui::help_modal` | Accessible shortcuts help popup modal (`HelpModal`), categorized reference cards, and auto-dismiss on `Esc`/`q`/`?`. |
| [`directive_modal.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/directive_modal.rs) | `ui::directive_modal` | Directive injection modal (`DirectiveModal`), priority selection (`DirectivePriority`: Low, Normal, High, Critical), text cursor input, and submit action. |
| [`directive_editor.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/directive_editor.rs) | `ui::directive_editor` | In-app multiline directive editor modal (`DirectiveEditorModal`) with line numbers, scrolling, cursor positioning, and `Ctrl+S` / `Ctrl+Enter` save action. |
| [`new_worker_modal.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/new_worker_modal.rs) | `ui::new_worker_modal` | Dynamic agent slot provisioning modal (`NewWorkerModal`), table of available host slots (`IdentityDiscovery`), and spawn action. |
| [`status_bar.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/status_bar.rs) | `ui::status_bar` | Accessible status bar displaying active worker ID, real slot ID, role title, PID, model, token counters, and alert badges. |
| [`worker_list.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/worker_list.rs) | `ui::worker_list` | Dynamic worker session list widget with real role titles, process states (`●`, `○`, `⚡`, `🚨`), task previews, and selection indicators. |
| [`split_panes.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/split_panes.rs) | `ui::split_panes` | Multiplexer widget supporting Single, Horizontal, Vertical, and Grid layouts with active focus borders and history scroll indicators. |
| [`gauges.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/gauges.rs) | `ui::gauges` | Real-time progress gauges for hourly quota, weekly quota, and CPU/RAM usage meters with theme-aware color thresholds. |
| [`terminal_screen.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/terminal_screen.rs) | `ui::terminal_screen` | Zero-overhead ANSI character matrix renderer supporting both live cell buffers and history scrollback slices (`from_owned_cells`). |
| [`theme.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/theme.rs) | `ui::theme` | Color palette tokens, accessible theme modes (Tokyo Night, High Contrast Dark/Light, Color-Blind), glyphs, and style helpers. |

---

## 3. Component Specifications & State Models

### 3.1 SessionPickerScreen (`session_picker.rs`)
- **State Model**:
  ```rust
  pub struct SessionPickerScreen {
      pub sessions: Vec<SessionRecord>,
      pub selected_index: usize,
      pub is_creating: bool,
      pub new_session_name: String,
      pub notice: Option<String>,
      store: Arc<SessionStore>,
      theme: Theme,
  }
  ```
- **Actions Emitted (`SessionPickerAction`)**:
  - `Open(SessionRecord)`: User pressed `Enter` on a session row; loads and restores all workers in that session.
  - `Create(String)`: User entered a session name in the inline dialog and pressed `Enter`.
  - `Delete(String)`: User pressed `d` to delete the selected session.
  - `Exit`: User pressed `q` or `Esc` to return to the multiplexer screen.
  - `None`: Internal navigation event (Up/Down arrows, typing in create prompt).
- **Keybindings**:
  - `↑` / `k`: Select previous session.
  - `↓` / `j`: Select next session.
  - `Enter`: Open selected session.
  - `n`: Trigger inline create session dialog.
  - `d`: Delete selected session.
  - `Esc` / `q`: Exit picker.

### 3.2 HelpModal (`help_modal.rs`)
- **State Model**:
  ```rust
  pub struct HelpModal {
      theme: Theme,
      is_open: bool,
  }
  ```
- **Structure**: Rendered as a centered modal popup (64x22) with `Clear` background. Displays categorized shortcut entries matching `agi.toml`:
  - *Swarm Navigation & Tabs*: `Tab`, `Shift+Tab`, `1..9`, `F5..F8`.
  - *Directives & Instructions*: `m` / `Ctrl+M` (Inject Directive), `d` / `Ctrl+D` (In-app Editor), `o` / `Ctrl+O` (External Editor).
  - *Layout & Multiplexing*: `s` (Toggle Horizontal/Vertical/Grid), `n` (Provision Worker Slot), `b` (Toggle Sidebar).
  - *Terminal & Lifecycle*: `Ctrl+C` (Interrupt), `q` / `Ctrl+Q` (Quit & Persist), `F4` / `Alt+T` (Cycle Themes).
- **Dismissal**: `Esc`, `q`, or `?`.

### 3.3 DirectiveModal (`directive_modal.rs`)
- **State Model**:
  ```rust
  pub struct DirectiveModal {
      pub worker_id: String,
      pub slot_id: String,
      pub role: String,
      pub message: String,
      pub cursor_pos: usize,
      pub priority: DirectivePriority,
      pub is_open: bool,
      pub theme: Theme,
  }
  ```
- **Priority Selector (`DirectivePriority`)**:
  - `Low`: Teal `#73dac2` (Priority 1)
  - `Normal`: Blue `#7aa2f7` (Priority 2)
  - `High`: Yellow/Amber `#e0af68` (Priority 3)
  - `Critical`: Red `#f7768e` (Priority 4)
- **Actions Emitted (`DirectiveModalAction`)**:
  - `Submit { worker_id, message, priority }`: Operator pressed `Enter`. The central loop dispatches an asynchronous call to `engine.session_manager.interrupt_and_inject()`.
  - `Cancel`: Operator pressed `Esc`.
- **Keybindings**:
  - `Tab` / `Shift+Tab`: Cycle priority levels.
  - `Alt+1` .. `Alt+4`: Directly jump to priority level 1..4.
  - `Char(c)` / `Backspace` / `Left` / `Right`: In-place directive text editing.
  - `Enter`: Submit.
  - `Esc`: Cancel.

### 3.4 DirectiveEditorModal (`directive_editor.rs`)
- **State Model**:
  ```rust
  pub struct DirectiveEditorModal {
      pub worker_id: String,
      pub slot_id: String,
      pub role: String,
      pub lines: Vec<String>,
      pub cursor_row: usize,
      pub cursor_col: usize,
      pub scroll_offset: usize,
      pub is_open: bool,
      pub theme: Theme,
  }
  ```
- **Features**:
  - Multiline text editing with automatic line insertion and line joining.
  - Line numbers gutter styled with muted theme colors.
  - Active line and cursor position highlighting (`[Row X, Col Y]`).
  - Auto-scrolling viewport following the cursor.
- **Actions Emitted (`DirectiveEditorAction`)**:
  - `Save(String)`: Dispatched on `Ctrl+S` or `Ctrl+Enter`. Updates the worker's instruction task in memory and forwards the new instructions to the worker PTY.
  - `Cancel`: Dispatched on `Esc`.

### 3.5 NewWorkerModal (`new_worker_modal.rs`)
- **State Model**:
  ```rust
  pub struct NewWorkerModal {
      pub slots: Vec<AgentSlot>,
      pub selected_index: usize,
      pub is_open: bool,
      pub theme: Theme,
  }
  ```
- **Features**:
  - Discovers installed host agent slots via `IdentityDiscovery::discover_slots()`.
  - Displays a clean Ratatui table showing: Slot ID (`agy[x]`), Role title, Model name, Token status badge (`[TOKEN]` vs `[NO TOKEN]`), and Status.
  - Selecting a slot dynamically provisions a new `WorkerSession` configured with isolated environment variables (`USERPROFILE`, `HOME`, `AGY_SLOT`, `ANTIGRAVITY_APP_DATA_DIR`).
- **Actions Emitted (`NewWorkerModalAction`)**:
  - `Spawn(AgentSlot)`: Dispatched on `Enter`.
  - `Cancel`: Dispatched on `Esc` or `q`.

---

## 4. Real Agent Identity & Role Indicators

Both `StatusBarWidget` and `WorkerListWidget` extract and render real agent identities:
- **Real Role Titles**: Dynamically parsed from `.gemini/GEMINI.md` (e.g. `Backend Logic & Systems Engineer`, `Frontend Engineer & UI Auditor`, `Primary Coordinator`).
- **Real Slot Identifiers**: Formatted as `{worker_id}:{slot_id} [{role}]` (e.g. `1:agy11 [Backend Systems]`).
- **Model Labels**: Formatted from discovered slot settings (e.g. `gemini-3.8-flash-high`).
- **Alert Badges**: Shape- and color-differentiated status pills:
  - `⚡ Worker Finished`: Idle worker awaiting operator review.
  - `🚨 Assistance Needed`: Critical alarm requiring manual intervention.
  - `Notice Pills`: Temporary notifications for session creation, deletion, or directive delivery.

---

## 5. Keyboard Ergonomics & Integration Shortcuts

| Hotkey / Shortcut | Target Screen / Modal | Behavior |
|---|---|---|
| `Ctrl+P` | Multiplexer -> Session Picker | Switch to interactive session picker screen |
| `?` | Multiplexer -> Help Modal | Toggle keyboard shortcuts reference popup |
| `m` / `Ctrl+M` | Multiplexer -> Directive Modal | Open directive injection modal for active worker |
| `d` / `Ctrl+D` | Multiplexer -> Directive Editor | Open in-app multiline directive editor |
| `n` | Multiplexer -> New Worker Modal | Open dynamic agent slot provisioning modal |
| `s` | Multiplexer | Cycle split layout: Single -> Horizontal -> Vertical -> Grid |
| `b` | Multiplexer | Toggle worker metadata & quota gauges sidebar |
| `Tab` / `Shift+Tab` | Multiplexer | Cycle active worker tab / pane focus |
| `1`..`9` / `F5`..`F8` | Multiplexer | Fast tab jump to worker #1..#9 |
| `PageUp` / `PageDown` | Multiplexer | Terminal history scrollback navigation |
| `F4` / `Alt+T` | All Screens | Cycle accessible theme mode (Tokyo Night <-> High Contrast <-> Color Blind) |
| `Ctrl+C` | Multiplexer | Send SIGINT interrupt to active worker PTY |
| `q` / `Ctrl+Q` | Multiplexer | Save session state and exit application |

---

## 6. Testing & Verification

The UI module includes comprehensive unit and integration tests:
- `ui::session_picker::tests`: Verifies session list navigation, create dialog, and delete action.
- `ui::help_modal::tests`: Verifies help popup open/close keybindings and layout rendering.
- `ui::directive_modal::tests`: Verifies priority cycling, text cursor editing, and submit action.
- `ui::directive_editor::tests`: Verifies multiline text editing, cursor navigation, and Ctrl+S save.
- `ui::new_worker_modal::tests`: Verifies slot discovery, selection navigation, and spawn action.
- `tests/ui_widgets_test.rs`: Full integration test suite rendering all widgets and modals using Ratatui `TestBackend`.

Run the entire UI test suite with:
```bash
cargo test --manifest-path tui-core/Cargo.toml --test ui_widgets_test
```
