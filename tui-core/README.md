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

## 2. Dual-Pane PTY Architecture & Vim-Style Modal Navigation

The compiled TUI interface replicates the Python `mind` workspace with a dual-pane PTY layout:
- **Left Pane (`#primary-pane`)**: Dedicated Primary Coordinator terminal (`agy1` / slot 1).
- **Right Pane (`#workers-pane`)**: Interactive Worker Multiplexer with visible Tab Bar (`1..9`) at the top and the active worker viewport below.

### Dual Vim-Style Modal System
The engine operates in two modal states:

1. **`NORMAL` (Command Mode)**:
   - `i`, `Enter`, `a`: Switches to `PTY_INTERACT` mode to type directly into child processes.
   - `Tab` / `Shift+Tab`: Toggles focus between Primary Coordinator and active Worker pane.
   - `1`..`9`: Fast jumps directly to worker tab #1 through #9 in the workers pane.
   - `h` / `l`: Cycles worker tabs in the workers pane left / right.
   - `s`: Toggles between 50/50 dual split and full-screen active pane.
   - `m` / `Ctrl+M`: Opens directive task injection modal.
   - `d` / `Ctrl+D`: Opens in-app multiline directive editor modal.
   - `o` / `Ctrl+O`: Opens directive file in external `$EDITOR`.
   - `c` / `n`: Opens new worker modal or provisions new agent slot.
   - `x`: Terminates and closes active worker tab in the workers pane.
   - `?`: Toggles shortcuts help modal.
   - `q`: Quits application safely.
   - `y`: Yanks / copies terminal buffer to clipboard.
   - `Ctrl+P`: Switches to full-screen interactive session picker.

2. **`PTY_INTERACT` (Insert Mode)**:
   - Keystrokes are passed raw directly into the focused child PTY.
   - **Leader Exits back to `NORMAL`**:
     * `Ctrl+B`: Immediate exit to Normal mode.
     * `F12`: Immediate exit to Normal mode.
     * `Esc Esc` (Double Escape within 350ms): Exits to Normal mode, while a single `Esc` is forwarded to the child PTY.

| Hotkey / Shortcut | Mode | Action | Description |
|---|---|---|---|
| `i` / `Enter` / `a` | Normal | `enter_pty` | Enter PTY Insert Mode |
| `Ctrl+B` / `F12` / `Esc Esc` | PtyInteract | `enter_normal` | Exit to Normal Command Mode |
| `Tab` / `Shift+Tab` | Normal | `switch_pane_focus` | Switch focus between Coordinator & Worker pane |
| `1`..`9` | Normal | `jump_worker_tab` | Fast jump to worker tab #1..#9 |
| `h` / `l` | Normal | `cycle_worker_tab` | Cycle worker tabs left / right |
| `s` | Normal | `toggle_split` | Toggle 50/50 Dual-Pane vs Full-Screen |
| `m` / `Ctrl+M` | Normal | `directive_modal` | Open Directive Injection Modal |
| `d` / `Ctrl+D` | Normal | `directive_editor` | Open In-app Directive Editor Modal |
| `o` / `Ctrl+O` | Normal | `open_external_editor` | Open directive file in system editor ($EDITOR) |
| `c` / `n` | Normal | `new_worker` | Open New Worker Modal to dynamically provision slot |
| `x` | Normal | `close_worker` | Close active worker tab in workers pane |
| `?` | Normal | `help` | Toggle shortcuts help modal |
| `q` / `Ctrl+Q` | Normal | `quit` | Save session state and exit application |
| `Ctrl+P` | Normal | `session_picker` | Open interactive full-screen session picker |

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
│       ├── session_picker.rs # Interactive session picker screen with inline session creation
│       ├── help_modal.rs # Accessible shortcuts reference card popup modal
│       ├── directive_modal.rs # Directive injection modal with priority cycling (Low/Normal/High/Critical)
│       ├── directive_editor.rs # In-app multiline directive editor with line numbers & Ctrl+S save
│       ├── new_worker_modal.rs # Dynamic slot discovery modal with isolated environment provisioning
│       ├── split_panes.rs # Flexible multiplexer (Single, Horiz, Vert, Grid) with history badges
│       ├── status_bar.rs  # Accessible status bar with real roles, metrics & alert badges
│       ├── gauges.rs      # Quota consumption & CPU/RAM progress gauges
│       ├── worker_list.rs # Dynamic navigable session list with real roles & accessible badges
│       └── terminal_screen.rs # High-efficiency ANSI ScreenCell renderer with scrollback support
└── tests/
    ├── README.md       # Integration test framework documentation
    ├── pty_test.rs     # Virtual buffer & PTY spawn tests
    ├── pty_burst_test.rs # PTY rapid burst, UTF-8 split chunks & interrupt stress
    ├── ui_widgets_test.rs # Ratatui ANSI cell matrix, themes, & scrollback tests
    ├── concurrency_multiplex_test.rs # Concurrent worker session multiplexing
    ├── ipc_test.rs     # JSON-RPC & MCP tool dispatch tests
    ├── session_test.rs # Session lifecycle, direct Alt jump, & resize tests
    ├── session_persistence_test.rs # Session serialization, atomic updates & pruning tests
    ├── host_slot_discovery_test.rs # Host slot discovery, role extraction & env isolation tests
    ├── shortcut_parity_test.rs # Python-parity shortcut key engine & TOML config tests
    └── modal_state_machine_test.rs # Modal dialog state machine & transition flow tests
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

### Run Formatted Sessions Table & Clean Inactive Sessions
```bash
# Formatted sessions table matching `mind sessions`
cargo run --bin agi -- sessions

# Output sessions as JSON
cargo run --bin agi -- sessions --json

# Clean / prune stale and empty sessions
cargo run --bin agi -- sessions --clean
```

### Run Comprehensive Diagnostic Doctor
```bash
# Comprehensive diagnostic doctor check matching `mind doctor`
cargo run --bin agi -- doctor
```

### Run Quota Usage Monitor Table
```bash
# Display quota usage monitor table matching `mind usage`
cargo run --bin agi -- usage

# Inspect specific slot or output JSON
cargo run --bin agi -- usage -s agy11
cargo run --bin agi -- usage --json
```

### Run Performance Benchmarks
```bash
cargo run --release --bin agi -- bench
```

### Run as Stdio FastMCP Server
```bash
cargo run --bin agi -- mcp
# or
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
