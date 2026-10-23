# `tui-core/tests/` — Automated Integration Test Suites

> **Comprehensive Automated Integration Test Framework** for the compiled multi-agent TUI engine.
> Maintained by Testing & Benchmarking Engineer (`agy100`).

---

## 1. Overview & Architectural Scope

The test harness in `tui-core/tests/` provides automated verification for the high-performance compiled TUI architecture. The test suite guarantees resilience across low-level portable-pty streaming, ANSI/VTE virtual screen state machine emulation, Ratatui Tokyo-Night visual widget rendering, concurrent worker session multiplexing, and Model Context Protocol (JSON-RPC 2.0) coordination.

Target system modules covered:
- **`pty::master` & `pty::process`**: Native pseudo-terminal spawning, asynchronous channel piping, signal interrupts (`SIGINT`), and window resize propagation (`SIGWINCH`).
- **`pty::buffer`**: In-memory 2D character matrix (`ScreenCell`), ANSI SGR attribute decoding (RGB 24-bit, 256-color, 16-color, bold, dim, italic, underline), scrollback history buffer, and $O(1)$ version-based dirty-frame caching.
- **`session::manager` & `session::worker`**: Multi-agent session lifecycle (`agy1` .. `agyN`), tab cycling, interactive prompt idle detection, and coordinator alarm routing.
- **`ipc::mcp_server` & `ipc::jsonrpc`**: Embedded MCP JSON-RPC 2.0 tools dispatching, tool calls, and alarm streaming.
- **`ui::*`**: Ratatui visual components (`TerminalScreenWidget`, `SplitPanesWidget`, `StatusBarWidget`, `QuotaGaugesWidget`, `WorkerListWidget`).

---

## 2. Itemized Breakdown of Test Files

| Test File | Test Suite Scope | Modules Tested | Key Assertions & Scenarios |
|---|---|---|---|
| [`pty_test.rs`](file:///home/pluto/projects/mind/tui-core/tests/pty_test.rs) | Baseline PTY & Virtual Buffer | `pty::buffer`, `pty::process` | ANSI sequence parsing, cursor positioning (`\x1b[row;colH`), scrollback history bounds, plain text rendering, and basic process spawn/echo. |
| [`pty_burst_test.rs`](file:///home/pluto/projects/mind/tui-core/tests/pty_burst_test.rs) | Rapid Data Bursts & Stress | `pty::buffer`, `pty::process`, `pty::master` | Ingestion of 2,000+ rapid ANSI bursts, monotonic buffer version increments, split multi-byte UTF-8 chunks (Arabic, Emojis, Box drawing), PTY reader queue saturation (300 bursts), interactive `SIGINT` interruption during active streaming, and dynamic geometry resizing during active I/O. |
| [`ui_widgets_test.rs`](file:///home/pluto/projects/mind/tui-core/tests/ui_widgets_test.rs) | Tokyo Night Widgets & ANSI Cells | `ui::*`, `pty::buffer` | Translation of ANSI 24-bit RGB / 256-color cells to Ratatui `Buffer`, $O(1)$ dirty-frame detection (`is_dirty`), `SplitPanes` geometries (`Single`, `Horizontal`, `Vertical`, `Grid`) with active focus indicators and placeholder slot handling, `StatusBar` badges (`WorkerFinished`, `AssistanceNeeded`, `Custom`), `QuotaGauges` adaptive color thresholds, and `WorkerList` stateful cursor navigation. |
| [`concurrency_multiplex_test.rs`](file:///home/pluto/projects/mind/tui-core/tests/concurrency_multiplex_test.rs) | Concurrent Swarm Multiplexing | `session::manager`, `session::worker`, `ipc::mcp_server` | Concurrent spawning of 8+ worker sessions via `join_all`, simultaneous tab navigation cycling (500 iterations) under concurrent input writes and screen queries, parallel MCP alarm generation and draining, broadcast terminal resizing, and concurrent graceful termination (`kill`). |
| [`session_test.rs`](file:///home/pluto/projects/mind/tui-core/tests/session_test.rs) | Session Lifecycle & Tab Order | `session::manager`, `session::worker` | Session registry, tab indexing (`next_session`, `prev_session`, `active_index`), input pass-through to PTY stdin, and rendered screen verification. |
| [`ipc_test.rs`](file:///home/pluto/projects/mind/tui-core/tests/ipc_test.rs) | Embedded MCP JSON-RPC Server | `ipc::mcp_server`, `ipc::jsonrpc` | JSON-RPC 2.0 serialization/deserialization, MCP `tools/list` schema validation, and tool dispatch (`list_workers`, `check_account_quotas`). |

---

## 3. Step-by-Step Instructions for Running Tests Locally

### Run All Integration and Unit Tests
```bash
cargo test --manifest-path tui-core/Cargo.toml
```

### Run a Specific Test Suite
```bash
# Run Rapid PTY Burst & Event Loop Stress Tests
cargo test --test pty_burst_test --manifest-path tui-core/Cargo.toml

# Run Visual UI Widgets & ANSI Rendering Tests
cargo test --test ui_widgets_test --manifest-path tui-core/Cargo.toml

# Run Concurrent Worker Multiplexing Tests
cargo test --test concurrency_multiplex_test --manifest-path tui-core/Cargo.toml

# Run MCP IPC Protocol Tests
cargo test --test ipc_test --manifest-path tui-core/Cargo.toml
```

### Run Tests with Full Tracing Output
```bash
RUST_LOG=debug cargo test --test pty_burst_test -- --nocapture
```

---

## 4. Critical Edge Cases, Validation Boundaries & Dependencies

1. **PTY Async Channel Backpressure:**
   - Rapid bursts (hundreds of lines emitted in milliseconds) must not drop bytes or deadlock the PTY read thread. Tokio mpsc channel buffer (256 slots) paired with dedicated async consumer tasks ensures smooth consumption.
2. **Fragmented Multi-Byte UTF-8 Sequences:**
   - Multi-byte UTF-8 sequences split arbitrarily across TCP / PTY chunks (such as Arabic glyphs or 4-byte Unicode emojis) are safely parsed through `vte::Parser` without panics or surrogate string corruption.
3. **Dirty-Frame Cache Precision ($O(1)$ Checks):**
   - The screen buffer version increments on every byte ingestion or geometry mutation. The UI renderer compares cached vs current buffer version in $O(1)$ time, skipping re-computation when the screen has not changed.
4. **Lock Ordering & Concurrency Deadlock Prevention:**
   - High concurrent contention across `SessionManager::sessions`, `WorkerSession::pty`, and `PtyProcess::buffer` is validated under simultaneous tab switching, alarm pushing, and background reader updating. No cyclic lock acquisition exists.
5. **Platform Independence:**
   - Tests automatically detect the host OS (`cfg!(windows)` vs Linux POSIX), using `cmd.exe` or `bash` accordingly.
