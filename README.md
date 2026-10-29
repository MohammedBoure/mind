# `mind` (`agi`)

> **Autonomous Multi-Agent AI Orchestration Engine & High-Performance Terminal Interface** — Built in Rust with Tokio, Ratatui, Portable-PTY, and FastMCP.

---

> [!NOTE]
> **Python Implementation Preservation**: The original Python implementation (`src/mind`) has been cleanly separated and fully preserved on the dedicated branch [`python-version`](https://github.com/MohammedBoure/mind/tree/python-version). The `main` branch is now centered on the native compiled Rust engine (`tui-core` / `agi`) for sub-millisecond event loops, zero-polling PTY multiplexing, and robust multi-agent orchestration without Python GIL bottlenecks.

---

## Architecture & Fleet Orchestration

`mind` transforms a developer workstation into a 200-agent autonomous software engineering fleet. Each agent operates inside an unprivileged Linux **Bubblewrap (`bwrap`)** sandbox with dedicated environment tokens and history while mounting the shared project repository.

```
+-----------------------------------------------------------------------------+
|                          mind / agi: Native Core                            |
+-----------------------------------------------------------------------------+
|                                  TuiEngine                                  |
|   ├── SessionManager                                                        |
|   │     ├── Coordinator Terminal (Slot 1..10)   -> PtyProcess -> Buffer     |
|   │     ├── Worker Terminal      (Slot 11..50)  -> PtyProcess -> Buffer     |
|   │     └── Worker Terminal      (Slot 51..200) -> PtyProcess -> Buffer     |
|   ├── EventLoop (Tokio async stream)                                        |
|   │     ├── Crossterm Events (Keys, Mouse, Window Resize)                   |
|   │     ├── Portable-PTY Streams (<1ms async channel)                       |
|   │     └── FastMCP Coordinator Alarms & Wakeup Bus                         |
|   └── Theme & Accessibility System (Tokyo Night, WCAG AAA High Contrast)     |
+-----------------------------------------------------------------------------+
                                       |
                   Bubblewrap Sandboxed Agent Fleet (`agys`)
             [ agy1: Orchestrator | agy11: Backend | agy100: Gatekeeper ]
                                       |
                       Shared Git Project Repository
```

---

## Comprehensive Workstation Setup Guide

For complete, step-by-step instructions on configuring host dependencies, setting up Bubblewrap sandboxing, managing agent tokens, and configuring the 200-agent deterministic fleet, see:

👉 **[`docs/ENVIRONMENT_SETUP_AND_AGENT_FLEET.md`](file:///home/pluto/projects/mind/docs/ENVIRONMENT_SETUP_AND_AGENT_FLEET.md)**

---

## Features

- **Compiled Native Speed** — Written in Rust with `tokio`, `ratatui`, `portable-pty`, and `crossterm`. Delivers sub-millisecond keystroke responsiveness and zero-polling async PTY multiplexing.
- **Dual-Pane Vim Workspace** —
  - **Left Pane**: Dedicated Primary Coordinator terminal (`agy1` .. `agy10`).
  - **Right Pane**: Tabbed Worker Multiplexer with active tabs (`1..9`) and slot search modal (`agy1..200`).
- **Namespace Sandboxing (`agys`)** — Unprivileged filesystem isolation per slot via `bwrap`. Independent `$HOME/.gemini`, separate shell history, and independent Google/Gemini token isolation with concurrency locks.
- **Deterministic Domain Specialization** —
  - `agy1` – `agy10`: Lead Orchestrators / Project Managers (`orchestrator`).
  - `agy11` – `agy50`: Backend Logic & Systems Engineers (`backend`).
  - `agy51` – `agy100`: Frontend & Interface Auditors (`frontend`).
  - `agy101` – `agy150`: Quality Gatekeepers & Pragmatic Test Engineers (`test`).
  - `agy151` – `agy200`: UX Finishing, Polish & Performance Specialists (`ux`).
- **FastMCP & Non-Blocking Coordination** —
  - `notify_coordinator_worker_idle`: Asynchronous completion alarms injected into the coordinator's event queue.
  - `/btw`: Non-interruptive side-channel inquiries between peer workers.
  - `/effort <level>`: Dynamic reasoning depth allocation before task dispatch.
- **Collective Quota Monitoring** — Visual terminal dashboard inspecting hourly and weekly consumption fractions across all configured accounts (`agys --usage`).

---

## Quickstart

### Prerequisites

- **Linux / POSIX** (Ubuntu 22.04+, Debian 12+, Fedora, Arch)
- **Rust Toolchain**: 1.80+ (`curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`)
- **Bubblewrap**: `sudo apt-get install -y bubblewrap`
- **Build Essentials**: `sudo apt-get install -y build-essential pkg-config libssl-dev`

### Compiling & Running `agi`

```bash
# Build optimized release binary from workspace root
cargo build --release -p tui-core --bin agi

# Launch interactive TUI
./target/release/agi

# Or run directly via Cargo
cargo run --release -p tui-core --bin agi
```

---

## Vim Modal Navigation

| Mode / Key | Action |
|---|---|
| **`NORMAL Mode`** | Default window navigation and slot management mode. |
| `i`, `Enter`, `a` | Switch to **`PTY_INTERACT`** mode to pass raw scancodes to child terminal. |
| `Tab` / `Shift+Tab` | Toggle focus between Primary Coordinator and active Worker pane. |
| `1` .. `9` | Fast jump directly to Worker Tab #1 through Tab #9. |
| `c` | Create a new worker tab. |
| `x` | Close the currently focused worker tab. |
| `w` | Open the **Worker Slot Selector Modal** (`agy1..200`) with live search. |
| `?` | Toggle quick Help Modal. |
| **`PTY_INTERACT Mode`** | Passes all keyboard inputs directly to the child pseudoterminal process. |
| `Ctrl+B`, `F12`, `Esc Esc` | Exit `PTY_INTERACT` mode and return to `NORMAL` mode immediately. |

---

## Repository Structure

```
mind/
├── docs/                               # Architecture and environment setup manuals
│   ├── ENVIRONMENT_SETUP_AND_AGENT_FLEET.md  # Complete workstation setup & fleet guide
│   ├── architecture_and_migration_guide.md   # Architectural specifications
│   ├── auth_refactor_architecture.md         # Authentication engine specifications
│   └── README.md                       # Documentation directory index
├── tui-core/                           # Native compiled Rust engine
│   ├── benches/                        # Performance and latency benchmark suites
│   ├── src/                            # Tokio PTY loop, Ratatui UI, and SessionManager
│   ├── tests/                          # Integration and E2E parity test suites
│   ├── Cargo.toml                      # Crate manifest
│   └── README.md                       # Detailed tui-core technical documentation
├── Cargo.toml                          # Root Cargo workspace manifest
├── Cargo.lock                          # Dependency lockfile
├── agent_assignments.json              # Active fleet dispatch registry
└── README.md                           # Main project overview
```

---

## Branches

- **`main`**: High-performance compiled native Rust architecture (`tui-core` / `agi`).
- **[`python-version`](https://github.com/MohammedBoure/mind/tree/python-version)**: Full, standalone historical Python implementation (`src/mind`).
