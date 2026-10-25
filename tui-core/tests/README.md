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
| [`ui_widgets_test.rs`](file:///home/pluto/projects/mind/tui-core/tests/ui_widgets_test.rs) | Accessible Widgets, Palettes & Scrollback | `ui::*`, `pty::buffer` | Translation of ANSI cells to Ratatui `Buffer`, $O(1)$ dirty-frame detection (`is_dirty`), `SplitPanes` geometries (`Single`, `Horizontal`, `Vertical`, `Grid`), scrollback history rendering (`test_split_panes_with_scrollback_rendering`), accessibility theme modes (`TokyoNight`, `HighContrastDark`, `HighContrastLight`, `ColorBlind`), color-blind safe badges, and `WorkerList` stateful navigation. |
| [`concurrency_multiplex_test.rs`](file:///home/pluto/projects/mind/tui-core/tests/concurrency_multiplex_test.rs) | Concurrent Swarm Multiplexing | `session::manager`, `session::worker`, `ipc::mcp_server` | Concurrent spawning of 8+ worker sessions via `join_all`, simultaneous tab navigation cycling (500 iterations) under concurrent input writes and screen queries, parallel MCP alarm generation and draining, broadcast terminal resizing, and concurrent graceful termination (`kill`). |
| [`session_test.rs`](file:///home/pluto/projects/mind/tui-core/tests/session_test.rs) | Session Lifecycle & Hotkey Jumping | `session::manager`, `session::worker` | Session registry, tab indexing (`next_session`, `prev_session`, `select_index`), direct `Alt+1`..`Alt+9` jumping, input pass-through, broadcast resize propagation, and graceful swarm shutdown (`shutdown_all`). |
| [`ipc_test.rs`](file:///home/pluto/projects/mind/tui-core/tests/ipc_test.rs) | Embedded MCP JSON-RPC Server | `ipc::mcp_server`, `ipc::jsonrpc` | JSON-RPC 2.0 serialization/deserialization, MCP `tools/list` schema validation, and tool dispatch (`list_workers`, `check_account_quotas`). |
| [`session_persistence_test.rs`](file:///home/pluto/projects/mind/tui-core/tests/session_persistence_test.rs) | Session Persistence & Clean Pruning | `session::session_store` | Verification of session file serialization (`~/.mind/sessions/<name>.json`), atomic updates and filename sanitization, telemetry tracking (`total_steps`, `total_interactions`, `last_activity`), descending sorting by `last_activity`, inactive/empty session pruning (`--clean`), and default session provisioning. |
| [`host_slot_discovery_test.rs`](file:///home/pluto/projects/mind/tui-core/tests/host_slot_discovery_test.rs) | Dynamic Host Slot Discovery & Isolation | `session::identity` | Dynamic slot scanning under `~/.local/share/agy-instances/agy[x]`, multi-tier role extraction priority (`agent_assignments.json` -> `.gemini/GEMINI.md` -> heuristics), settings model detection, JWT token payload base64 email parsing, isolated environment variable provisioning (`USERPROFILE`, `HOME`, `AGY_SLOT`), and live filesystem discovery. |
| [`shortcut_parity_test.rs`](file:///home/pluto/projects/mind/tui-core/tests/shortcut_parity_test.rs) | Shortcut Engine & Python Parity | `session::shortcuts` | Exact Python-parity shortcuts (`q`, `?`, `Tab`, `Shift+Tab`, `BackTab`, `m`, `d`, `o`, `s`, `n`, `1`..`9`), pass-through for unmapped keys, custom TOML configuration loading (`~/.config/mind/agi.toml`), and conflict-free tab switching. |
| [`modal_state_machine_test.rs`](file:///home/pluto/projects/mind/tui-core/tests/modal_state_machine_test.rs) | Modal State Transitions & Screen Flow | `ui::*` | Modal open/close state transitions (`HelpModal`), `DirectiveModal` priority cycling (Normal -> High -> Critical -> Low) and input submission/cancellation, `DirectiveEditorModal` multiline buffer navigation, line editing, saving, and cancelling, `NewWorkerModal` slot selection & spawn dispatch, and `SessionPickerScreen` list navigation, creation, opening, deleting, and exit actions. |
| [`parity_e2e_test.rs`](file:///home/pluto/projects/mind/tui-core/tests/parity_e2e_test.rs) | Python 1:1 Parity End-to-End Suite | `ui::workspace`, `ui::header_bar`, `ui::bottom_bar`, `session::manager`, `main` | End-to-end verification of dual-pane coordinator/worker multiplexer, Vim dual-mode (`NORMAL` vs `PTY_INTERACT`) and leader exits (`Esc Esc` within 350ms, `Ctrl+B`, `F12`), Zellij-style 1-line top dock pills (brand logo, session pill, mode badge, active worker count, quota progress bar, MCP status), bottom action pills and architecture badge, and CLI subcommands (`doctor`, `usage`, `usage --json`, `sessions`, `sessions --clean`, `bench`). |
| [`auto_spawn_agy_test.rs`](file:///home/pluto/projects/mind/tui-core/tests/auto_spawn_agy_test.rs) | Auto-Spawn Real `agy` CLI & Slot Isolation | `session::identity`, `session::worker`, `session::manager`, `session::shortcuts` | Verification of automatic `agy` CLI detection (`/home/pluto/.local/bin/agy`, `/usr/local/bin/agy`, `which agy`), Coordinator slot 1 environment isolation (`USERPROFILE`, `HOME`, `AGY_SLOT=1`, `AGY_INSTANCE_DIR`), Worker slot [x] environment isolation, `AgiConfig` `auto_spawn_agy` option, command resolution, and graceful fallback to system shell. |

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

# Run Session Persistence & Pruning Tests
cargo test --test session_persistence_test --manifest-path tui-core/Cargo.toml

# Run Host Slot Discovery & Isolation Tests
cargo test --test host_slot_discovery_test --manifest-path tui-core/Cargo.toml

# Run Python-Parity Shortcut Engine Tests
cargo test --test shortcut_parity_test --manifest-path tui-core/Cargo.toml

# Run Modal State Machine Tests
cargo test --test modal_state_machine_test --manifest-path tui-core/Cargo.toml

# Run Python 1:1 Parity End-to-End Tests
cargo test --test parity_e2e_test --manifest-path tui-core/Cargo.toml

# Run Auto-Spawn Real agy CLI & Slot Isolation Tests
cargo test --test auto_spawn_agy_test --manifest-path tui-core/Cargo.toml
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
6. **Atomic Session Persistence & Filename Sanitization:**
   - Session store updates write to hidden temporary files before atomic filesystem rename (`rename`), preventing half-written corrupted states upon sudden power loss or process kill. Unsafe characters (`/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`) in session names are sanitized to `_`.
7. **Multi-Tier Agent Slot Discovery & Environment Isolation:**
   - Dynamic host discovery traverses instances and falls back gracefully when `.gemini/GEMINI.md` or `settings.json` is absent. Environment variables (`USERPROFILE`, `HOME`, `AGY_SLOT`, `ANTIGRAVITY_APP_DATA_DIR`) are strictly mapped to each agent slot's directory to ensure complete file-system isolation.
8. **Shortcut Engine Conflict Resolution:**
   - Custom keybindings configured in `~/.config/mind/agi.toml` override defaults without collisions. Unmapped keystrokes automatically pass through as raw terminal bytes to the active child PTY.
9. **Modal State Stack Transition Safety:**
   - Modal dialogs (`HelpModal`, `DirectiveModal`, `DirectiveEditorModal`, `NewWorkerModal`) manage encapsulated lifecycle states. Modals safely capture input while active and cleanly return control to the underlying screen upon submission or dismissal (`Esc`), preventing trapped focus states.
10. **Vim Dual-Mode State Machine & 350ms Leader Exit Threshold:**
    - Modal engine transitions between `NORMAL` and `PTY_INTERACT`. Escaping raw PTY pass-through without dropping single Esc commands (e.g., in vim inside child PTY) is handled through an exact 350ms double-escape detection window, or immediate `Ctrl+B` / `F12` escape keys.
11. **Auto-Spawning Real `agy` CLI & Slot Isolation Provisioning:**
    - Automatic detection locates executable `agy` binary across standard host locations (`/home/pluto/.local/bin/agy`, `/usr/local/bin/agy`, `which agy`). If unavailable or non-executable, the session manager transparently falls back to the system shell. When slot instance directories do not yet exist, they are automatically provisioned to prevent child process `chdir(HOME)` `ENOENT` failures.


