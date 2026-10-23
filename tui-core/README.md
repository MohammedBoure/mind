# `tui-core` — Compiled TUI Engine Architecture

> **High-Performance Compiled Multi-Agent TUI Engine** — Written in Rust with Tokio, Portable-PTY, Crossterm, Ratatui, and MCP (JSON-RPC 2.0).

---

## 1. Overview & Architectural Role

`tui-core` is the native compiled engine powering the `mind` multi-agent orchestrator. It replaces the legacy Python TUI core with an ultra-low-latency, zero-polling asynchronous systems architecture designed to multiplex dozens of concurrent AI agent worker terminals (`agy1` .. `agyN`) without UI lag or GIL contention.

```
+-----------------------------------------------------------------------------+
|                          tui-core: Central Engine                           |
+-----------------------------------------------------------------------------+
|                                  TuiEngine                                  |
|   ├── SessionManager                                                        |
|   │     ├── WorkerSession ("coordinator") -> PtyProcess -> ScreenBuffer     |
|   │     ├── WorkerSession ("agy2")        -> PtyProcess -> ScreenBuffer     |
|   │     └── WorkerSession ("agy3")        -> PtyProcess -> ScreenBuffer     |
|   ├── EventLoop (Tokio async stream)                                        |
|   │     ├── Crossterm Events (Keys, Mouse, Resize)                          |
|   │     ├── POSIX SIGWINCH Handler (SignalKind::window_change)              |
|   │     ├── PTY I/O Streams (<1ms async channel)                            |
|   │     └── Alarms & Periodic Ticks                                         |
|   ├── Theme & Accessibility System                                          |
|   │     ├── Tokyo Night (Default)                                           |
|   │     ├── High Contrast Dark (WCAG AAA)                                   |
|   │     ├── High Contrast Light (Daylight visible)                          |
|   │     └── Color-Blind Accessible (Okabe-Ito universal design)             |
|   └── MCP Bridge                                                            |
|         ├── EmbeddedMcpServer (Stdio / JSON-RPC 2.0 tool dispatcher)        |
|         └── McpClient (HTTP SSE / REST connector to port 8765)              |
+-----------------------------------------------------------------------------+
```

---

## 2. Keyboard Navigation & Python-Parity Configurable Shortcuts

The interactive compiled TUI interface offers ergonomic, single-keystroke navigation controls across all sessions, views, themes, and scrollback histories. Shortcuts can be customized via `~/.config/mind/agi.toml` (or `~/.mind/config.toml`):

| Hotkey / Shortcut | Action | Description |
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
| `PageUp` / `Shift+Up` | `Action::ScrollUp` | Scrolls active terminal history backward (5 lines per step) |
| `PageDown` / `Shift+Down` | `Action::ScrollDown` | Scrolls active terminal history forward toward live bottom |
| `b` | UI Toggle | Toggle worker metadata & quota sidebar |
| `F4` / `Alt+T` | Theme Toggle | Switch active color palette: Tokyo Night -> HC Dark -> HC Light -> Color-Blind |
| Any Typing / Enter | Terminal Input | Delivers keystroke to child PTY and automatically resets scroll offset |
| `Ctrl+C` | Send SIGINT | Delivers interrupt signal (0x03) to the currently active worker PTY |

---

## 3. Persistent Sessions & Real Slot Discovery

1. **Persistent Sessions (`~/.mind/sessions/<name>.json`)**:
   - `SessionStore` persists multi-agent sessions, activity telemetry (`total_steps`, `total_interactions`, `last_activity`), and worker configurations.
   - Provides atomic write guarantees using sibling temporary files before atomic renames.
   - Automatically prunes stale/inactive sessions with `clean_sessions()`.

2. **Real Agent Slot Identity (`IdentityDiscovery`)**:
   - Dynamically scans `/home/pluto/.local/share/agy-instances/agy[x]`.
   - Parses real roles from `.gemini/GEMINI.md` and models from `antigravity-cli/settings.json`.
   - Proactively builds slot-isolated environments (`USERPROFILE`, `HOME`, `AGY_SLOT`, `ANTIGRAVITY_APP_DATA_DIR`).

---

## 4. Responsive Terminal Resizing (SIGWINCH Architecture)

The engine implements robust, tearing-free terminal resizing capable of dynamically adapting to arbitrary window dimensions:

1. **Dual Resize Detection**:
   - Captures standard POSIX `SIGWINCH` signals via `tokio::signal::unix::{signal, SignalKind::window_change()}`.
   - Concurrently monitors Crossterm `Event::Resize(cols, rows)`.
   - Queries system terminal geometry with zero lag.

2. **PTY Worker Propagation**:
   - Broadcasts updated terminal geometry (`portable_pty::PtySize`) across all active worker PTYs via `session_manager.broadcast_resize(rows, cols)`.
   - Signals running child shells and processes to reformat output to the new geometry.

3. **ANSI Virtual Screen Buffer Resizing (`ScreenBuffer::resize`)**:
   - **No Character Clipping**: When the viewport shrinks vertically, overflow rows from the top of the viewport are shifted into `scrollback` history, keeping active command lines and prompts in view.
   - **No Text Tearing**: Cursor coordinates are shifted proportionally with the viewport shift to maintain cursor alignment.
   - **History Unrolling**: When expanding vertically, lines from recent `scrollback` are restored into the viewport, avoiding blank gaps.
   - **Column Dynamic Padding / Truncation**: Columns are resized across both live cells and scrollback history.
   - **Memory Leak Prevention**: Scrollback history is strictly capped at `max_scrollback` (2000 lines).

---

## 4. Accessibility Palettes & Themes

The UI provides four comprehensive theme palettes via `ThemeMode` and `ThemePalette`:

1. **Tokyo Night (Default)**:
   - Deep background `#1a1b26`, surface `#24283b`, foreground `#c0caf5`, and neon accents (cyan `#7dcfff`, magenta `#bb9af7`, blue `#7aa2f7`).
2. **High Contrast Dark**:
   - Pitch-black background `#000000`, pure white text `#ffffff`, and hyper-saturated borders/badges. Meets WCAG AAA contrast ratios for low-vision users.
3. **High Contrast Light**:
   - Pure white background `#ffffff`, dark ink text `#0f0f14`, and deep saturated accents. Engineered for bright sunlight and daylight environments.
4. **Color-Blind Accessible (Protanopia / Deuteranopia Safe)**:
   - Built on Okabe & Ito (2008) universal color design.
   - Eliminates red-green confusion by utilizing Sky Blue (`#56B4E9`), Amber/Yellow (`#F0E442`), and Vermilion (`#D55E00`).
   - Reinforced with distinct text badges: `[!] Assistance Needed`, `[⚡] Worker Finished`, and `[OK] Normal`.

---

## 5. Directory & Module Structure

```
tui-core/
├── Cargo.toml          # Rust package dependencies & configuration
├── README.md           # Architecture, component APIs & UX guide
├── BENCHMARKS.md       # Empirical benchmark results & comparative analysis vs Python
├── benches/
│   ├── README.md       # Benchmark harness documentation & instructions
│   └── benchmarks.rs   # Standalone benchmark binary harness
├── src/
│   ├── README.md       # Source root documentation
│   ├── lib.rs          # TuiEngine root exports and unified facade
│   ├── main.rs         # Compiled CLI binary (TUI runner, MCP server, benchmarks)
│   ├── benchmarks.rs   # Comprehensive performance benchmark implementation
│   ├── error.rs        # Error taxonomy (TuiError, Result)
│   ├── pty/            # Low-level PTY execution & ANSI virtual screen
│   │   ├── README.md   # PTY master, screen buffer, and resizing docs
│   │   ├── mod.rs
│   │   ├── master.rs   # Native PTY master loop (portable-pty)
│   │   ├── process.rs  # PtyProcess wrapper with async buffer updates
│   │   └── buffer.rs   # ScreenBuffer 2D character matrix & vte parser
│   ├── events/         # Tokio event loop & Crossterm input multiplexer
│   │   ├── README.md   # Tokio event loop, POSIX SIGWINCH, and event types
│   │   ├── mod.rs
│   │   ├── types.rs    # AppEvent (Key, Mouse, Resize, Alarm, Tick)
│   │   └── event_loop.rs # Async event loop stream with SIGWINCH handler
│   ├── ipc/            # MCP client/server & JSON-RPC 2.0
│   │   ├── README.md   # JSON-RPC 2.0 and MCP tool bridge
│   │   ├── mod.rs
│   │   ├── types.rs    # JSON-RPC & MCP protocol structures
│   │   ├── jsonrpc.rs  # Framing & parsing helpers
│   │   ├── mcp_client.rs # Async HTTP/SSE client
│   │   └── mcp_server.rs # Embedded stdio/in-memory MCP server
│   ├── session/        # Agent session orchestration & tab switching
│   │   ├── README.md   # Session manager, identity discovery, and shortcuts docs
│   │   ├── mod.rs
│   │   ├── identity.rs # Dynamic host agy[x] slot discovery and environment isolation
│   │   ├── session_store.rs # Persistent storage at ~/.mind/sessions/<name>.json
│   │   ├── shortcuts.rs # Configurable shortcut engine (~/.config/mind/agi.toml)
│   │   ├── worker.rs   # WorkerSession (state, PTY, scrollback offset, idle detection)
│   │   └── manager.rs  # SessionManager & McpBackend implementation
│   └── ui/             # Accessible visual Ratatui widgets
│       ├── README.md   # Comprehensive UI documentation & API specifications
│       ├── mod.rs      # Public exports & widget facade
│       ├── theme.rs    # Accessible themes (Tokyo Night, HC Dark, HC Light, Color-Blind)
│       ├── split_panes.rs # Flexible multiplexer (Single, Horiz, Vert, Grid) with history badges
│       ├── status_bar.rs  # Accessible status bar with metrics & alert badges
│       ├── gauges.rs      # Quota consumption & CPU/RAM progress gauges
│       ├── worker_list.rs # Dynamic navigable session list with accessible badges
│       └── terminal_screen.rs # High-efficiency ANSI ScreenCell renderer with scrollback support
└── tests/
    ├── README.md       # Integration test framework documentation
    ├── pty_test.rs     # Virtual buffer & PTY spawn tests
    ├── pty_burst_test.rs # PTY rapid burst, UTF-8 split chunks & interrupt stress
    ├── ui_widgets_test.rs # Ratatui ANSI cell matrix, themes, & scrollback tests
    ├── concurrency_multiplex_test.rs # Concurrent worker session multiplexing
    ├── ipc_test.rs     # JSON-RPC & MCP tool dispatch tests
    └── session_test.rs # Session lifecycle, direct Alt jump, & resize tests
```

---

## 7. Build, Test & CLI Command Suite

### Run Integration Tests
```bash
cargo test
```

### Launch Interactive AGI TUI
```bash
# Launch default/active session or Session Picker
cargo run --bin agi

# Create and launch new session named 'alpha_mission'
cargo run --bin agi -- new alpha_mission

# Inspect saved sessions
cargo run --bin agi -- sessions

# Clean / prune stale and empty sessions
cargo run --bin agi -- sessions --clean
```

### Run Performance Benchmarks
```bash
cargo run --release --bin agi -- bench
```

### Run as Stdio MCP Server
```bash
cargo run --bin agi -- --mcp-stdio
```

---

## 7. Performance Benchmarks Summary

| Benchmark Metric | Compiled Rust Core (`tui-core`) | Legacy Python Textual Baseline | Real-World Improvement |
|---|---|---|---|
| **Frame Latency (80x24)** | **104.75 µs (0.10 ms)** | ~15,000 - 30,000 µs (15-30 ms) | **~150x – 280x Faster** |
| **High-Res Latency (160x50)** | **422.38 µs (0.42 ms)** | ~40,000 - 85,000 µs (40-85 ms) | **~95x – 200x Faster** |
| **Dashboard Frame (Full UI)** | **267.46 µs (0.27 ms)** | ~25,000 - 45,000 µs (25-45 ms) | **~93x – 168x Faster** |
| **Dirty-Frame Checking** | **0.00 ns** ($O(1)$ integer check) | Not Supported (Full re-layout) | **Zero-Cost Bypass** |
| **PTY Ingestion Rate** | **951,750 ops/sec** | ~35,000 - 60,000 ops/sec | **~16x – 27x Faster** |
| **ANSI Parser Throughput** | **78.97 MB/sec** | ~2.5 – 5.0 MB/sec | **~16x – 31x Higher** |
| **Memory Footprint (8 Workers)** | **6.58 MB RSS** | ~150 - 240 MB (GIL runtime) | **>95% Memory Reduction** |
| **Marginal Memory per Worker** | **~56 KB** / worker | ~15 - 20 MB / worker | **~260x Less Memory** |
| **CPU Load @ 100 FPS Updates** | **6.28% CPU** | ~45% – 75% CPU (GIL-bound) | **~7x – 12x Less CPU** |

> For complete statistical analysis and comparative graphs, see [`BENCHMARKS.md`](file:///home/pluto/projects/mind/tui-core/BENCHMARKS.md).
