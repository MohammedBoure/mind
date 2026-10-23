# UI Widgets & Visual Components (`tui-core/src/ui`)

> **Frontend & UX Polish Architecture Specification** for the compiled multi-agent TUI engine.
> Maintained by Polish & Ergonomics Engineer (`agy151`) using Rust, Ratatui 0.29, and Crossterm 0.28.

---

## 1. Overview & Architecture

The `ui` module provides a comprehensive suite of reusable, reactive, accessible visual widgets engineered for low-latency terminal multiplexing across dozens of concurrent AI agent worker terminals (`agy1` .. `agyN`).

The module completely decouples backend PTY process buffers and MCP events from Ratatui presentation, providing:
- **Dirty-Frame Caching**: $O(1)$ integer version comparisons eliminate redundant re-rendering when screen buffers have not mutated.
- **Accessible Theme Palettes**: Runtime theme cycling across Tokyo Night, High Contrast Dark (WCAG AAA), High Contrast Light, and Color-Blind Universal Design (Protanopia / Deuteranopia safe).
- **Responsive Split Multiplexing**: Single pane, horizontal split, vertical split, and 2x2 quad grid with active focus highlighting.
- **Scrollback History Exploration**: Per-session scrolling offset (`PageUp`/`PageDown` or `Shift+Up`/`Shift+Down`) with instant scroll position indicator badges (`[SCROLL -N]`).
- **Real-Time Visual Alerts**: Dedicated coordinator alarm pills with shape- and color-differentiated status badges.

```
+-----------------------------------------------------------------------------------+
|                         tui-core Visual UI Hierarchy                              |
+-----------------------------------------------------------------------------------+
| Top Header: Tabs [ ▶ coordinator:agy1 [Alt+1] | worker-build:agy2 [Alt+2] ]        |
|             + QuotaGaugesWidget (Hourly Quota, Weekly Quota, CPU, RAM)            |
+-----------------------------------+-----------------------------------------------+
| Left Sidebar (F1/Alt+B toggle):   | Main Area: SplitPanesWidget                   |
| ├── WorkerListWidget              | ├── SplitMode::Single (1-Pane)                |
| │   ├── ● agy1:coordinator (pid)  | ├── SplitMode::Horizontal (Side-by-side)      |
| │   ├── ⚡ agy2:worker-build [DONE]| ├── SplitMode::Vertical (Stacked)             |
| │   └── 🚨 agy3:worker-bench [HELP]| └── SplitMode::Grid (2x2 Quad Panes)          |
| └── QuotaGaugesWidget (Vertical)  |                                               |
|     (Hourly, Weekly, CPU, RAM)    | TerminalScreenWidget: ANSI ScreenCell Matrix  |
|                                   | with scrollback history support [SCROLL -N]   |
+-----------------------------------+-----------------------------------------------+
| Bottom: StatusBarWidget (Accessible Theme Mode)                                   |
| [ ● coordinator:agy1 ] [ PID: 1234 ] [ 🤖 claude-3-5-sonnet ] [ 📊 Tokens: 18.5k ] |
| [ ⚡ Worker Finished / 🚨 Assistance Needed ] [ [SPLIT: HORIZ] ] [ Hotkeys Guide ]|
+-----------------------------------------------------------------------------------+
```

---

## 2. Itemized File Breakdown

| File | Module | Responsibility |
|---|---|---|
| [`mod.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/mod.rs) | `ui` | Public module exports, widget facade, and re-exports (`Theme`, `ThemeMode`, `ThemePalette`). |
| [`theme.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/theme.rs) | `ui::theme` | Color palette tokens, accessible theme modes (Tokyo Night, High Contrast Dark/Light, Color-Blind), typography, glyphs, and style helpers. |
| [`split_panes.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/split_panes.rs) | `ui::split_panes` | Multiplexer widget supporting Single, Horizontal, Vertical, and Grid layouts with active focus borders, title badges, and history scroll indicators. |
| [`status_bar.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/status_bar.rs) | `ui::status_bar` | Accessible status bar displaying active worker ID, slot ID, PID, AI model, token status, and color-blind safe alert badges. |
| [`gauges.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/gauges.rs) | `ui::gauges` | Real-time progress gauges for hourly quota, weekly quota, and CPU/RAM usage meters with theme-aware color thresholds. |
| [`worker_list.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/worker_list.rs) | `ui::worker_list` | Dynamic worker session list with status icons (`●`, `○`, `⚡`, `🚨`), task previews, and accessible selection cursors. |
| [`terminal_screen.rs`](file:///home/pluto/projects/mind/tui-core/src/ui/terminal_screen.rs) | `ui::terminal_screen` | Zero-overhead ANSI character matrix renderer supporting both live cell buffers and history scrollback slices (`from_owned_cells`). |

---

## 3. Keyboard Ergonomics & Shortcuts

| Shortcut | Scope | Behavior |
|---|---|---|
| `Tab` | Swarm Navigation | Focuses next worker tab in sequence. |
| `Shift+Tab` / `BackTab` | Swarm Navigation | Focuses previous worker tab in sequence. |
| `Alt+1` .. `Alt+9` | Swarm Navigation | Directly switches focus to worker session #1 through #9. |
| `F2` / `Alt+S` | Pane Multiplexing | Cycles layout mode: `Single` -> `Horizontal` -> `Vertical` -> `Grid`. |
| `F1` / `Alt+B` | Sidebar Toggle | Collapses or expands the left worker list and resource sidebar. |
| `F4` / `Alt+T` | Theme Switcher | Cycles active theme: `TokyoNight` -> `HighContrastDark` -> `HighContrastLight` -> `ColorBlind`. |
| `PageUp` / `Shift+Up` | Terminal History | Scrolls active terminal scrollback upward (view older output). |
| `PageDown` / `Shift+Down` | Terminal History | Scrolls active terminal scrollback downward (toward live output). |
| Keystrokes / Enter | Terminal Input | Delivers input to active child PTY and automatically resets scroll offset to live view. |
| `Ctrl+C` | Process Control | Delivers SIGINT interrupt (0x03) to active worker process. |
| `Ctrl+Q` | Application Lifecycle | Gracefully cleans up child PTY processes, disables raw mode, and exits cleanly. |

---

## 4. Theme Modes & Accessibility Design Tokens

The styling architecture provides complete visual accessibility via `ThemeMode` and `ThemePalette`:

### 4.1 Tokyo Night (Default)
- **Background**: `#1a1b26` (Dark), `#24283b` (Surface), `#292e42` (Highlight)
- **Foreground**: `#c0caf5` (Light), `#565f89` (Muted)
- **Accents**: Cyan `#7dcfff`, Blue `#7aa2f7`, Magenta `#bb9af7`, Yellow `#e0af68`, Green `#9ece6a`, Red `#f7768e`
- **Use Case**: Default immersive developer palette for dark environments.

### 4.2 High Contrast Dark (WCAG AAA)
- **Background**: `#000000` (Pure Black), `#141414` (Surface)
- **Foreground**: `#ffffff` (Pure White), `#b4b4b4` (Muted)
- **Accents**: Saturated Cyan `#00ffff`, Yellow `#ffff00`, Red `#ff3c3c`, Green `#00ff00`
- **Use Case**: Maximum contrast for visually impaired or low-vision users.

### 4.3 High Contrast Light
- **Background**: `#ffffff` (Pure White), `#f0f2f5` (Surface)
- **Foreground**: `#0f0f14` (Dark Charcoal), `#50555f` (Muted)
- **Accents**: Deep Navy `#0046c8`, Dark Teal `#007878`, Crimson `#c80000`, Amber `#b47300`
- **Use Case**: Daylight and well-lit office environments requiring light backgrounds.

### 4.4 Color-Blind Accessible (Protanopia / Deuteranopia Safe)
- **Design Standard**: Okabe & Ito (2008) Universal Color Palette.
- **Background**: `#12161e` (Dark), `#1c2330` (Surface)
- **Accents**:
  - Sky Blue `#56B4E9`: Replaces green for healthy states, normal badges, and border focus.
  - Amber `#F0E442`: Represents completed tasks, warnings, and moderate quotas.
  - Vermilion `#D55E00`: Distinct high-visibility red-orange for blockers and alerts.
  - Strong Blue `#0072B2`: Secondary status indicator.
  - Reddish Purple `#CC79A7`: Model and metadata indicator.
- **Reinforced Badges**:
  - `[OK] Normal`: Text + shape reinforcement.
  - `[⚡] Worker Finished`: Lightning icon + bracketed tag.
  - `[!] Assistance Needed`: Warning exclamation + high-contrast Vermilion pill.

---

## 5. Viewport & Scrollback History Architecture

When browsing terminal output:
1. `WorkerSession` maintains a synchronized `scroll_offset: Arc<Mutex<usize>>`.
2. When `scroll_offset == 0`, live screen rows from `ScreenBuffer::cells()` are rendered with zero copying.
3. When `scroll_offset > 0`, `ScreenBuffer::viewport_cells(scroll_offset, height)` calculates the visible window across `scrollback` history and active screen cells.
4. Pane titles immediately display `[SCROLL -N]` so the operator always knows their viewport position.
5. Delivering keyboard input to the terminal automatically resets `scroll_offset` to 0, ensuring the operator sees immediate response to their commands.

---

## 6. Guidelines on Loading, Empty & Placeholder States

- **Empty Slot States**: When a split layout pane has no associated worker session, `SplitPanesWidget` renders a clean placeholder with inactive borders and clear instructions: `"No worker attached to this slot. Press Tab / Alt+1-9 to switch or spawn via MCP."`
- **Process State Icons**:
  - `●` Running (Active PTY execution)
  - `○` Idle (Resting at interactive shell/agy prompt)
  - `⚡` Done (Task completed or alarm fired)
  - `🚨` Alert (Agent assistance required)
  - `⏸` Interrupted (SIGINT pause)
  - `⏹` Exited (Child process terminated)
