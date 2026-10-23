# UI Widgets & Visual Components (`tui-core/src/ui`)

> **Frontend & UI/UX Architecture Specification** for the compiled multi-agent TUI engine.
> Implemented by `agy51` (Frontend & Interface Auditor) using Rust, Ratatui 0.29, and Crossterm 0.28.

---

## 1. Overview & Architecture

The `ui` module provides a comprehensive suite of reusable, reactive, Tokyo-Night styled visual widgets engineered for low-latency terminal multiplexing across dozens of concurrent AI agent worker terminals (`agy1` .. `agyN`).

The module decouples backend PTY process buffers and MCP events from Ratatui presentation, providing dirty-frame caching ($O(1)$ version checks), ANSI cell-matrix translation, split layout multiplexing, and real-time visual alerts.

```
+-----------------------------------------------------------------------------------+
|                         tui-core Visual UI Hierarchy                              |
+-----------------------------------------------------------------------------------+
| Top Header: Tabs [ coordinator | worker-build | worker-bench ]                    |
|             + QuotaGaugesWidget (Hourly Quota, Weekly Quota, CPU, RAM)            |
+-----------------------------------+-----------------------------------------------+
| Left Sidebar (F1 to toggle):      | Main Area: SplitPanesWidget                   |
| ├── WorkerListWidget              | ├── SplitMode::Single (1-Pane)                |
| │   ├── ● agy1:coordinator (pid)  | ├── SplitMode::Horizontal (Side-by-side)      |
| │   ├── ⚡ agy2:worker-build [DONE]| ├── SplitMode::Vertical (Stacked)             |
| │   └── 🚨 agy3:worker-bench [HELP]| └── SplitMode::Grid (2x2 Quad Panes)          |
| └── QuotaGaugesWidget (Vertical)  |                                               |
|     (Hourly, Weekly, CPU, RAM)    | TerminalScreenWidget: ANSI ScreenCell Matrix  |
+-----------------------------------+-----------------------------------------------+
| Bottom: StatusBarWidget (Tokyo Night Theme)                                       |
| [ ● coordinator:agy1 ] [ PID: 1234 ] [ 🤖 claude-3-5-sonnet ] [ 📊 Tokens: 18.5k ] |
| [ ⚡ Worker Finished / 🚨 Assistance Needed ] [ [SPLIT: HORIZ] ] [ Hotkeys Guide ]|
+-----------------------------------------------------------------------------------+
```

---

## 2. Itemized File Breakdown

| File | Module | Responsibility |
|---|---|---|
| [`mod.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/mod.rs) | `ui` | Public module exports, widget facade, and re-exports. |
| [`theme.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/theme.rs) | `ui::theme` | Tokyo Night color palette tokens (`#1a1b26`), standard typography, glyphs (`●`, `○`, `⚡`, `🚨`), and style helpers. |
| [`split_panes.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/split_panes.rs) | `ui::split_panes` | Flexible split layout widget supporting Single, Horizontal, Vertical, and 2x2 Grid multiplexing with active focus highlighting. |
| [`status_bar.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/status_bar.rs) | `ui::status_bar` | Sleek Tokyo-Night status bar displaying active worker ID, slot ID, PID, AI model, token status, and visual alert badges. |
| [`gauges.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/gauges.rs) | `ui::gauges` | Real-time progress gauges for hourly quota remaining, weekly quota remaining, and CPU/RAM usage meters. |
| [`worker_list.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/worker_list.rs) | `ui::worker_list` | Navigable worker session list widget with status icons (`●`, `○`, `⚡`, `🚨`), task previews, and selection cursors. |
| [`terminal_screen.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/terminal_screen.rs) | `ui::terminal_screen` | High-efficiency Ratatui widget translating low-level ANSI `ScreenCell` matrix directly to double-buffered Ratatui cells with dirty-frame checking. |

---

## 3. Component Interfaces, Properties (Props) & State Models

### 3.1 `SplitPanesWidget`
Multiplexes multiple terminal screens into configurable grid or split geometry.

```rust
use tui_core::ui::{SplitMode, SplitPanesWidget};

let widget = SplitPanesWidget::new(SplitMode::Horizontal)
    .sessions(engine.sessions())
    .focused_index(active_index)
    .ratio(50, 50)
    .show_cursor(true);

f.render_widget(widget, chunks[1]);
```

- **Props / Configuration**:
  - `mode: SplitMode`: `Single` (1 full pane), `Horizontal` (Left/Right), `Vertical` (Top/Bottom), `Grid` (2x2 Quad).
  - `sessions: Vec<Arc<WorkerSession>>`: Managed worker sessions.
  - `focused_index: usize`: Index of active session receiving keyboard pass-through.
  - `ratio(first: u16, second: u16)`: Percentage split between primary and secondary panes.
  - `show_cursor: bool`: Toggle block cursor in focused terminal.

### 3.2 `StatusBarWidget`
Renders Tokyo Night pill segments and coordinator alert badges.

```rust
use tui_core::ui::{AlertBadge, StatusBarWidget};

let status_bar = StatusBarWidget::from_session(&session, "claude-3-5-sonnet")
    .split_mode("HORIZ-SPLIT")
    .custom_hint("Tab: Next │ F2: Split │ ^C: Int │ ^Q: Quit");

f.render_widget(status_bar, chunks[2]);
```

- **Alert Badges**:
  - `AlertBadge::WorkerFinished(msg)`: Displays vibrant yellow badge `[ ⚡ Worker Finished <msg> ]`.
  - `AlertBadge::AssistanceNeeded(msg)`: Displays critical red alert `[ 🚨 Assistance Needed <msg> ]`.
  - `AlertBadge::Custom(msg, style)`: Custom status pill.
- **Metrics Displayed**:
  - Active worker ID (`coordinator`), slot ID (`agy1`), process ID (`PID: 2314`).
  - Model indicator (`🤖 claude-3-5-sonnet`).
  - Token consumption meter (`📊 Tokens: 18.5k / 200k (9.2%)`).

### 3.3 `QuotaGaugesWidget`
Displays visual progress gauges for quota consumption and system load.

```rust
use tui_core::ui::{GaugeLayout, QuotaGaugesWidget};

let gauges = QuotaGaugesWidget::new()
    .hourly_remaining(85.0)  // 85% remaining
    .weekly_remaining(92.0)  // 92% remaining
    .cpu_usage(24.5)         // 24.5% CPU
    .memory(2780, 8192)      // 2.7GB / 8.1GB RAM
    .layout(GaugeLayout::Horizontal);

f.render_widget(gauges, header_right);
```

- **Layout Modes**:
  - `GaugeLayout::Horizontal`: 4 column gauges side-by-side with percent labels.
  - `GaugeLayout::Vertical`: Stacked line gauges suited for compact sidebar monitors.
- **Adaptive Gradient Thresholds**:
  - Quota Remaining: Green (>50%), Yellow (20-50%), Red (<20% quota warning).
  - Resource Usage: Teal/Cyan (<60%), Orange (60-85%), Red (>85% saturation).

### 3.4 `WorkerListWidget`
Interactive session list widget with status icons and indicators.

```rust
use tui_core::ui::WorkerListWidget;

let list = WorkerListWidget::from_sessions(&sessions, Some(active_idx))
    .block(Block::default().borders(Borders::ALL).title(" Workers "));

f.render_widget(list, sidebar_top);
```

- **Status Glyphs**:
  - `●` (Green / Cyan): Active process running.
  - `○` (Muted gray): Process idle / waiting at interactive prompt.
  - `⚡` (Yellow): Worker finished alarm.
  - `🚨` (Red): Worker needs assistance / blocked alarm.
  - `⏸` (Orange): Process interrupted (SIGINT).
  - `⏹` (Dark gray): Process exited.

### 3.5 `TerminalScreenWidget`
High-speed ANSI cell matrix renderer.

```rust
use tui_core::ui::TerminalScreenWidget;

let buf_lock = session.buffer();
let screen_buffer = buf_lock.lock();

let widget = TerminalScreenWidget::from_buffer(&screen_buffer)
    .show_cursor(true)
    .scroll_offset(0);

f.render_widget(widget, pane_inner);
```

- **Features**:
  - Direct conversion of `ScreenCell` (`fg`, `bg`, `bold`, `dim`, `italic`, `underline`) to Ratatui `Cell` styling.
  - $O(1)$ dirty-frame checking via `widget.is_dirty(cached_version)`.
  - Block cursor rendering with reverse video and Tokyo Night cyan highlight.
  - Scrollback history viewing via `scroll_offset`.

---

## 4. Visual Design Tokens & Tokyo Night Theme

| Token | Hex | RGB | Semantic Usage |
|---|---|---|---|
| `BG_DARK` | `#1a1b26` | `(26, 27, 38)` | Terminal background, gauge troughs, dark borders |
| `BG_SURFACE` | `#24283b` | `(36, 40, 59)` | Status bar background, header container surfaces |
| `BG_HIGHLIGHT` | `#292e42` | `(41, 46, 66)` | Selected list row background, active pane titles |
| `FG_LIGHT` | `#c0caf5` | `(192, 202, 245)` | Primary text, normal terminal characters |
| `FG_MUTED` | `#565f89` | `(86, 95, 137)` | Inactive pane borders, separator bars, PID text |
| `ACCENT_BLUE` | `#7aa2f7` | `(122, 162, 247)` | Active worker pill background |
| `ACCENT_CYAN` | `#7dcfff` | `(125, 207, 255)` | Active pane borders, cursor highlight, selection pointer |
| `ACCENT_GREEN` | `#9ece6a` | `(158, 206, 106)` | Running status icon, abundant quota gauge |
| `ACCENT_TEAL` | `#73daca` | `(115, 218, 202)` | Token status segment, task descriptions |
| `ACCENT_YELLOW` | `#e0af68` | `(224, 175, 104)` | Tab underline, `⚡ Worker Finished` alert badge |
| `ACCENT_ORANGE` | `#ff9e64` | `(255, 158, 100)` | Moderate resource load, interrupted state |
| `ACCENT_RED` | `#f7768e` | `(247, 118, 142)` | `🚨 Assistance Needed` alert badge, critical quota |
| `ACCENT_MAGENTA`| `#bb9af7` | `(187, 154, 247)` | AI model indicator pill, split mode label |

---

## 5. Keyboard Navigation & Interactive Controls

When running the interactive multiplexer (`cargo run -- run`), the following hotkeys are available:

| Key Binding | Action |
|---|---|
| `Tab` | Focus next worker session in tab order |
| `Shift + Tab` | Focus previous worker session |
| `F2` or `Alt + S` | Cycle split mode: `Single` -> `Horizontal` -> `Vertical` -> `Grid` -> `Single` |
| `F1` or `Alt + B` | Toggle left sidebar visibility (Agent list + system gauges) |
| `F3` | Toggle test alert badge (`⚡ Worker Finished` / `🚨 Assistance Needed`) |
| `Ctrl + C` | Send `SIGINT` (Ctrl+C) to the currently focused worker PTY process |
| `Ctrl + Q` | Cleanly restore terminal state and quit application |
| Regular typing | Transparent pass-through of characters, Enter, Backspace, and Arrow keys directly to the active worker PTY |

---

## 6. Testing & Verification

All widgets have comprehensive unit test coverage:
```bash
cargo test --lib ui
```
Outputs:
```text
running 10 tests
test ui::split_panes::tests::test_split_mode_cycle ... ok
test ui::terminal_screen::tests::test_dirty_frame_checking ... ok
test ui::terminal_screen::tests::test_terminal_screen_widget_cell_rendering ... ok
test ui::status_bar::tests::test_status_bar_rendering_with_badges ... ok
test ui::status_bar::tests::test_status_bar_alert_assistance_needed ... ok
test ui::worker_list::tests::test_worker_list_widget_render ... ok
test ui::gauges::tests::test_vertical_gauges_render ... ok
test ui::split_panes::tests::test_split_panes_render_single ... ok
test ui::split_panes::tests::test_split_panes_geometry ... ok
test ui::gauges::tests::test_horizontal_gauges_render ... ok

test result: ok. 10 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.01s
```
