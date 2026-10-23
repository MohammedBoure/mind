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
|   │     ├── PTY I/O Streams (<1ms async channel)                            |
|   │     └── Alarms & Periodic Ticks                                         |
|   └── MCP Bridge                                                            |
|         ├── EmbeddedMcpServer (Stdio / JSON-RPC 2.0 tool dispatcher)        |
|         └── McpClient (HTTP SSE / REST connector to port 8765)              |
+-----------------------------------------------------------------------------+
```

---

## 2. Directory & Module Structure

```
tui-core/
├── Cargo.toml          # Rust package dependencies & configuration
├── README.md           # Architecture, component APIs & agy51 UI guide
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
│   │   ├── README.md
│   │   ├── mod.rs
│   │   ├── master.rs   # Native PTY master loop (portable-pty)
│   │   ├── process.rs  # PtyProcess wrapper with async buffer updates
│   │   └── buffer.rs   # ScreenBuffer 2D character matrix & vte parser
│   ├── events/         # Tokio event loop & Crossterm input multiplexer
│   │   ├── README.md
│   │   ├── mod.rs
│   │   ├── types.rs    # AppEvent (Key, Mouse, Resize, Alarm, Tick)
│   │   └── event_loop.rs # Async event loop stream
│   ├── ipc/            # MCP client/server & JSON-RPC 2.0
│   │   ├── README.md
│   │   ├── mod.rs
│   │   ├── types.rs    # JSON-RPC & MCP protocol structures
│   │   ├── jsonrpc.rs  # Framing & parsing helpers
│   │   ├── mcp_client.rs # Async HTTP/SSE client
│   │   └── mcp_server.rs # Embedded stdio/in-memory MCP server
│   ├── session/        # Agent session orchestration & tab switching
│   │   ├── README.md
│   │   ├── mod.rs
│   │   ├── worker.rs   # WorkerSession (state, PTY, idle detection)
│   │   └── manager.rs  # SessionManager & McpBackend implementation
│   └── ui/             # Tokyo Night visual Ratatui widgets (built by agy51)
│       ├── README.md   # Comprehensive UI documentation & API specifications
│       ├── mod.rs      # Public exports & widget facade
│       ├── theme.rs    # Tokyo Night colors, typography & glyphs
│       ├── split_panes.rs # Flexible multiplexer (Single, Horiz, Vert, Grid)
│       ├── status_bar.rs  # Sleek status bar with metrics & alert badges
│       ├── gauges.rs      # Quota consumption & CPU/RAM progress gauges
│       ├── worker_list.rs # Dynamic navigable session list
│       └── terminal_screen.rs # High-efficiency ANSI ScreenCell renderer
└── tests/
    ├── README.md       # Integration test framework documentation
    ├── pty_test.rs     # Virtual buffer & PTY spawn tests
    ├── pty_burst_test.rs # PTY rapid burst, UTF-8 split chunks & interrupt stress
    ├── ui_widgets_test.rs # Ratatui ANSI cell matrix & widget rendering
    ├── concurrency_multiplex_test.rs # Concurrent worker session multiplexing
    ├── ipc_test.rs     # JSON-RPC & MCP tool dispatch tests
    └── session_test.rs # Session lifecycle & tab switching tests
```

---

## 3. Component APIs for UI Engineer (`agy51`)

`agy51` can directly utilize the following public APIs to build visual widgets (split panes, status bars, real-time gauges, and dynamic lists):

### 3.1 Initializing the Engine

```rust
use tui_core::TuiEngine;

let engine = TuiEngine::new(50, "http://127.0.0.1:8765");
```

### 3.2 Spawning Worker Sessions

```rust
use std::collections::HashMap;

let session = engine.spawn_worker(
    "agy2",              // ID
    "agy2",              // Slot ID
    "bash",              // Command ("powershell.exe" on Windows)
    vec![],              // Args
    None,                // Working directory
    HashMap::new(),      // Isolated environment variables
    24,                  // Initial rows
    80,                  // Initial cols
)?;
```

### 3.3 Querying Sessions & Active Tab

```rust
// Get all registered sessions in tab order:
let sessions = engine.sessions();

// Get the index of the currently focused tab:
let active_idx = engine.session_manager.active_index();

// Switch to a specific tab:
engine.session_manager.select_index(target_index);

// Tab cycling:
engine.session_manager.next_session();
engine.session_manager.prev_session();

// Access the currently active session:
if let Some(active) = engine.active_session() {
    println!("Active worker: {}", active.id);
}
```

### 3.4 Rendering Terminal Content in Ratatui

`agy51` has two ways to render terminal content:

1. **Clean Plain Text (Fast & Simple):**
   ```rust
   let lines_to_render = 30;
   let text = session.get_screen_text(lines_to_render);
   let widget = ratatui::widgets::Paragraph::new(text);
   ```

2. **Full ANSI Character Grid (Direct Cell Matrix):**
   ```rust
   let buf_lock = session.pty.lock().buffer();
   let buffer = buf_lock.lock();
   let cells: &[Vec<ScreenCell>] = buffer.cells();
   // ScreenCell contains: c (char), fg (CellColor), bg (CellColor), bold, italic, underline
   ```

3. **Dirty-Frame Checking ($O(1)$ Version Counter):**
   ```rust
   let current_version = session.version();
   // Only recalculate layout/styling if current_version != cached_version
   ```

### 3.5 Handling Keyboard & Terminal Events

```rust
use tui_core::events::AppEvent;
use crossterm::event::KeyCode;

while let Some(event) = engine.next_event().await {
    match event {
        AppEvent::Key(key) => {
            if key.code == KeyCode::Tab {
                engine.session_manager.next_session();
            } else if let KeyCode::Char(c) = key.code {
                // Pass keystroke to active worker's terminal:
                engine.send_input_to_active(&c.to_string(), false).ok();
            }
        }
        AppEvent::Resize(rows, cols) => {
            // Propagate terminal resize to all active PTY processes:
            engine.resize_all(rows, cols);
        }
        AppEvent::Alarm(alarm) => {
            // Display visual badge (e.g. ⚡ Worker Finished or 🚨 Help Needed):
            println!("Alarm from {}: {}", alarm.worker_id, alarm.message);
        }
        AppEvent::Tick => {
            // Periodic UI animation / gauge refresh
        }
        _ => {}
    }
}
```

---

## 4. UI Widgets & Visual Architecture (Built by `agy51`)

`tui-core/src/ui` provides Tokyo-Night styled visual components for terminal multiplexing:

### 4.1 Split Panes Widget (`SplitPanesWidget`)
- Supports layout modes: `SplitMode::Single` (1-pane), `SplitMode::Horizontal` (side-by-side), `SplitMode::Vertical` (stacked), and `SplitMode::Grid` (2x2 quad multiplexer).
- Highlights the active focused pane with glowing Tokyo Night cyan/magenta borders and title focus indicators.

### 4.2 Status Bar Widget (`StatusBarWidget`)
- Displays active worker ID, slot ID, PID, AI model (`claude-3-5-sonnet`), and token consumption status (`18.5k / 200k`).
- Dynamic visual alert badges:
  - `⚡ Worker Finished`: Triggered upon agent task completion or idle detection.
  - `🚨 Assistance Needed`: Triggered on agent blocker alarms.

### 4.3 Real-Time Gauges (`QuotaGaugesWidget`)
- Progress gauges for hourly remaining quota and weekly remaining quota.
- Real-time CPU and Memory utilization meters with adaptive green -> yellow -> red threshold styling.
- Flexible layouts: `GaugeLayout::Horizontal` (top banner) and `GaugeLayout::Vertical` (sidebar monitor).

### 4.4 Dynamic Lists (`WorkerListWidget`)
- Navigable worker session list displaying status indicators (`●` Running, `○` Idle, `⚡` Done, `🚨` Alert, `⏸` Interrupted, `⏹` Exited), process IDs, and current tasks.

### 4.5 Terminal Screen Widget (`TerminalScreenWidget`)
- Renders the virtual ANSI character matrix (`ScreenCell`) directly to double-buffered Ratatui cells.
- Features $O(1)$ dirty-frame checking to eliminate redundant re-renders when the screen version counter is unchanged.

See [`tui-core/src/ui/README.md`](file:///home/pluto/projects/mind/tui-core/src/ui/README.md) for detailed widget APIs and props.

---

## 5. MCP & JSON-RPC Connectivity

`tui-core` provides dual MCP integration:

1. **Embedded MCP Server (`EmbeddedMcpServer`):**
   Can be run over Stdio (`cargo run -- --mcp-stdio`) to expose real-time worker controls directly to `agy`:
   - `list_workers`: Query all worker PIDs, statuses, and slots.
   - `get_terminal_screen`: Query rendered text for any worker.
   - `send_terminal_input`: Inject input into any worker.
   - `interrupt_and_inject`: Send SIGINT pause and inject priority directives.
   - `check_account_quotas`: Query remaining quota steps.
   - `notify_coordinator_worker_idle`: Emit completion alarms.
   - `notify_coordinator_help`: Request coordinator assistance.
   - `check_coordinator_alarms`: Read pending alarm notifications.

2. **MCP Client (`McpClient`):**
   Connects to existing `mind-mcp` HTTP servers running on port 8765.

---

## 6. Build, Test & Benchmark Commands

### Run Integration Tests
```bash
cargo test
```

To run individual test suites:
```bash
cargo test --test pty_burst_test          # PTY rapid burst & stress tests
cargo test --test ui_widgets_test         # Tokyo Night widgets & ANSI rendering
cargo test --test concurrency_multiplex_test # Concurrent worker multiplexing
```

### Run Performance Benchmarks
```bash
# Run release benchmark suite via CLI
cargo run --release -- bench

# Or via cargo bench
cargo bench
```

### Run Interactive TUI Multiplexer
```bash
cargo run -- run
```

### Run as Stdio MCP Server
```bash
cargo run -- --mcp-stdio
```

---

## 7. Performance Benchmarks & Empirical Results

The compiled Rust architecture (`tui-core`) replaces the legacy Python implementation (`Textual`, `Rich`, `Pyte`), achieving order-of-magnitude gains in rendering latency, memory efficiency, and throughput:

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

> For the comprehensive benchmark methodology, statistical percentile distributions, and technical breakdown, see [`BENCHMARKS.md`](file:///home/pluto/projects/mind/tui-core/BENCHMARKS.md).

