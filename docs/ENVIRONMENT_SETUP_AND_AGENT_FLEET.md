# Antigravity Multi-Agent Fleet: Environment Setup & Workstation Orchestration Guide

> Comprehensive technical blueprint for preparing a developer workstation to host, isolate, and orchestrate up to 200 concurrent autonomous Antigravity CLI (`agy`) agent instances managed via `agys` and the compiled high-performance Rust TUI engine (`agi` / `tui-core`).

---

## 1. System Overview & Architecture

The `mind` architecture transforms a Linux or POSIX workstation into an autonomous multi-agent development environment. Rather than running a monolithic assistant or executing uncoordinated background scripts, the system establishes a fleet of deterministically specialized agent slots (`agy1` through `agy200`).

Each agent operates within an isolated namespace sandbox powered by Linux **Bubblewrap (`bwrap`)**, maintaining dedicated shell history, cache, directives, and authentication tokens, while collaboratively binding to the shared Git repository workspace. The entire fleet is multiplexed and steered in real-time by the native compiled Rust engine (`agi`).

```
+---------------------------------------------------------------------------------------------------+
|                                        WORKSTATION HOST                                           |
|                                                                                                   |
|  +---------------------------------------------------------------------------------------------+  |
|  |                            agi (Native Rust TUI Engine: tui-core)                           |  |
|  |  +---------------------------------------+-----------------------------------------------+  |  |
|  |  |  Primary Coordinator (Slot 1..10)    |  Active Worker Tabs (Slots 11..200)           |  |  |
|  |  |  - Lead Orchestration & Strategy     |  - Worker PTY Multiplexer (Ratatui/Tokio)     |  |  |
|  |  |  - FastMCP Control & Alarm Bus       |  - Real-Time Virtual Screen Buffer            |  |  |
|  |  +---------------------------------------+-----------------------------------------------+  |  |
|  +---------------------------------------------------------------------------------------------+  |
|                                                  |                                                |
|             +------------------------------------+------------------------------------+           |
|             |                                    |                                    |           |
|             v                                    v                                    v           |
|   +-------------------+                +-------------------+                +-------------------+ |
|   | agy1 (Orchestrator)                | agy11 (Backend)   |                | agy100 (Gatekeeper) |
|   | bwrap Sandbox     |                | bwrap Sandbox     |                | bwrap Sandbox     | |
|   | - isolated ~/.gemini               | - isolated ~/.gemini               | - isolated ~/.gemini |
|   | - agy1.token      |                | - agy11.token     |                | - agy100.token    | |
|   +-------------------+                +-------------------+                +-------------------+ |
|             \                                    |                                   /            |
|              +-----------------------------------+----------------------------------+             |
|                                                  v                                                |
|                               [ Shared Git Project Workspace ]                                    |
|                                  /home/.../projects/mind                                          |
|                        - All instances bind to the live repo                              |
|                        - Branch conventions per domain range                              |
|                        - Synchronized via Git & MCP Bus                                   |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. Host System Prerequisites & Workstation Preparation

To ensure maximum stability, zero-latency process multiplexing, and robust filesystem sandboxing, configure the host environment according to the specifications below.

### 2.1 Operating System & Kernel Capabilities

- **Recommended OS**: Linux (Ubuntu 22.04 LTS / 24.04 LTS, Debian 12+, Arch Linux, or Fedora).
- **Kernel User Namespaces**: Bubblewrap requires unprivileged user namespaces. Verify this capability on the host:
  ```bash
  # Check if unprivileged user namespaces are enabled (should return 1)
  sysctl kernel.unprivileged_userns_clone 2>/dev/null || cat /proc/sys/kernel/unprivileged_userns_clone
  ```
  If disabled, enable it persistently:
  ```bash
  sudo sysctl -w kernel.unprivileged_userns_clone=1
  echo "kernel.unprivileged_userns_clone=1" | sudo tee /etc/sysctl.d/99-userns.conf
  ```

### 2.2 Mandatory System Packages

Install the required core development libraries, sandbox isolation utilities, and headless X11 automation tools:

```bash
sudo apt-get update && sudo apt-get install -y \
  bubblewrap \
  build-essential \
  pkg-config \
  libssl-dev \
  git \
  curl \
  jq \
  xdotool \
  x11-utils \
  scrot \
  maim \
  libxdo-dev
```

#### Package Roles:
- **`bubblewrap` (`bwrap`)**: The security foundation that enables unprivileged containerization, isolated `$HOME` paths per slot, and shared workspace mounting without requiring Docker daemons or root privileges.
- **`build-essential`, `pkg-config`, `libssl-dev`**: Required for compiling the high-performance native Rust core.
- **`xdotool`, `scrot`/`maim`, `libxdo-dev`**: Required for Testing and Gatekeeper agents (`agy100`–`agy150`) executing automated GUI perception, Vision Grid coordinate capture, and simulated human mouse/keyboard interactions.

### 2.3 Rust Toolchain Installation

The primary orchestrator engine (`agi`) is compiled natively in Rust:

```bash
# Install rustup and stable toolchain
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source "$HOME/.cargo/env"

# Verify toolchain version (Rust 1.80+ recommended)
rustc --version
cargo --version
```

### 2.4 Antigravity CLI (`agy`) Setup

Ensure the Google Antigravity CLI (`agy`) is installed and accessible in the user binary path:

```bash
# Verify agy installation
which agy || ls -la ~/.local/bin/agy

# Add ~/.local/bin to PATH in ~/.bashrc or ~/.zshrc if not already present
export PATH="$HOME/.local/bin:$PATH"
```

---

## 3. Multi-Instance Architecture (`agys`) & Sandboxing

The multi-instance manager script (`agys`) acts as the hypervisor for all agent environments.

### 3.1 Instance Storage Layout

All isolated instance environments reside under `$HOME/.local/share/agy-instances/` (customizable via the environment variable `AGY_INSTANCES_DIR`):

```
$HOME/.local/share/agy-instances/
├── agy1/                         # Lead Orchestrator instance
│   ├── .gemini/                  # Isolated instance Gemini configuration
│   │   ├── GEMINI.md             # Role directives & principles
│   │   ├── config/               # Instance-specific configuration
│   │   └── antigravity-cli/      # Cache and runtime state
│   ├── .bash_history             # Dedicated shell history
│   └── token.json                # Active authentication token for Slot 1
├── agy11/                        # Backend Engineer instance
│   ├── .gemini/
│   ├── .bash_history
│   └── token.json
├── agy51/                        # Frontend Auditor instance
├── agy100/                       # Quality Gatekeeper instance
└── agy151/                       # UX Finishing Specialist instance
```

### 3.2 Namespace Sandboxing via Bubblewrap (`bwrap`)

When an instance is invoked (e.g., `agys -r 11` or directly via command `agy11`), `agys` executes `bwrap` with targeted mount bindings:

```bash
bwrap \
  --ro-bind / / \
  --dev /dev \
  --proc /proc \
  --tmpfs /tmp \
  --bind "$inst_dir" "$HOME" \
  --bind "$PWD" "$PWD" \
  --bind "$inst_dir/.gemini" "$HOME/.gemini" \
  --setenv HOME "$HOME" \
  --setenv AGY_INSTANCE_ID "$inst_id" \
  --setenv AGY_INSTANCE_ROLE "$role" \
  ...
```

#### Why This Sandboxing Model is Essential:
1. **Zero Configuration Contamination**: Each agent maintains its own token, shell history, and cache. No agent can accidentally overwrite or invalidate another agent's active session.
2. **Seamless Workspace Collaboration**: The host project working directory (`$PWD`) is mounted directly into each instance's container. Every agent sees and interacts with the exact same Git repository simultaneously.
3. **Host Tooling Pass-Through**: Compilers (`cargo`, `rustc`), interpreters, Git credentials, and SSH keys remain available inside the sandbox without redundant container installation steps.

### 3.3 Dynamic CLI Aliases & Command Dispatch

To allow instantaneous terminal access to any slot, `agys` provides automatic dynamic symlinks in `~/.local/bin`:

```bash
# Direct slot execution pattern:
agy1      # Launches isolated Lead Orchestrator
agy11     # Launches isolated Backend Engineer
agy51     # Launches isolated Frontend Auditor
agy100    # Launches isolated Testing Gatekeeper
agy151    # Launches isolated UX Specialist
```

#### Administrative CLI Commands:
```bash
# List all active instances, roles, and status
agys --list

# View the collective quota consumption and reset countdowns across all accounts
agys --usage

# Synchronize role templates, repair symlinks, and update system rules
agys --sync

# Delete a specific instance environment
agys --delete <N>
```

---

## 4. Deterministic Slot Hierarchy & Agent Specialization

The fleet operates on a strict **deterministic domain partitioning** model across slots `1` through `200`. Every slot ID maps to a specialized operational role with dedicated responsibilities, branch conventions, and authority levels:

| Slot Range | Domain / Role Title | Git Branch Prefix | Primary Responsibility & Authority |
|---|---|---|---|
| **`agy1` – `agy10`** | **Lead Orchestrator**<br>`(Project Manager)` | Oversees `main` & `develop` | Strategic roadmap decomposition, first-turn parallel dispatch, high-level governance, release integration. **Strict rule:** Never reads raw source code or writes implementation logic directly. |
| **`agy11` – `agy50`** | **Backend Logic & Systems**<br>`(Systems Engineer)` | `backend/agy[x]-<feature>` | Core business logic, database migrations, PTY mechanics, systems algorithms, API contracts, and high-performance backend pipelines. |
| **`agy51` – `agy100`** | **Frontend & Interface**<br>`(UI/UX Auditor)` | `frontend/agy[x]-<component>` | Terminal widgets, Ratatui rendering components, web user interfaces, modal dialogs, accessibility standards, and responsive state bindings. |
| **`agy101` – `agy150`** | **Quality Gatekeeper**<br>`(Testing Engineer)` | `test/agy[x]-<scope>` | **Exclusive merge authority** for integrating feature branches into `develop`. Pragmatic verification, headless pilot testing, Vision Grid coordinate inspection, and natural input validation. |
| **`agy151` – `agy200`** | **UX Finishing & Polish**<br>`(Performance Specialist)` | `ux/agy[x]-<polish>` | Non-invasive presentation finishing, interaction feedback, micro-animations, asset size minimization, responsive edge-cases, and status line indicators. |

---

## 5. Functional Operational Recommendations & Governance

To maintain order and high velocity across up to 200 concurrent agents, all instances adhere to the following governance rules and functional patterns:

### 5.1 First-Turn Parallel Task Decomposition
When the Lead Orchestrator (`agy1`) receives a high-level directive or feature specification, it must **never** execute the implementation alone. In its very first turn, it decomposes the objective into specialized domain tasks and dispatches them in parallel to the respective worker slots (`agy11..50`, `agy51..100`, etc.) using FastMCP terminal input tools.

### 5.2 Dynamic Reasoning Effort Allocation (`/effort`)
Before dispatching any assignment to a worker agent, the orchestrator evaluates cognitive complexity and tunes the target agent's reasoning depth to optimize output quality while preserving account quotas:
- **`high` / `max`**: For complex system architectures, algorithmic cores, PTY low-level streaming, and gatekeeper test verification (`agy11..50`, `agy101..150`).
- **`medium`**: For standard UI components, modal dialogues, and routine refactoring (`agy51..100`, `agy151..200`).
- **`low`**: For status checks, simple sanity runs, or trivial git operations.

*Pre-Dispatch Pattern:*
```bash
# Tune effort immediately prior to task dispatch
send_terminal_input(worker_id="agy11", text="/effort high", press_enter=True)
send_terminal_input(worker_id="agy11", text="Implement the async PTY event stream...", press_enter=True)
```

### 5.3 Non-Interruptive Peer Requests (`/btw`)
Workers are authorized and encouraged to collaborate with peers or query the coordinator without disrupting ongoing execution chains.
- By wrapping queries in `/btw`, the message enters the recipient's background queue without triggering an immediate interrupt:
  ```text
  /btw [from agy51]: Does the backend endpoint return ISO-8601 timestamps with timezone offsets?
  ```
- Send via: `send_terminal_input(worker_id="agy11", text="/btw [from agy51]: ...", press_enter=True)`.

### 5.4 Asynchronous Completion Alarms (`notify_coordinator_worker_idle`)
Polling loops consume excessive CPU and exhaust rate limits. Whenever any worker finishes an assigned task or reaches an idle prompt, it must dispatch an asynchronous completion notification:
- **Tool call**: `notify_coordinator_worker_idle(worker_id="agy[x]", status_summary="...")`
- This injects a high-priority alarm event directly into the coordinator's event queue so the orchestrator resumes execution smoothly.

### 5.5 Mandatory English Directory Documentation (`README.md`)
Every code directory, component module, asset collection, or style package created or modified by any agent must contain a dedicated `README.md` written strictly in **English**.
- The documentation must detail:
  1. The architectural purpose of the directory.
  2. An itemized breakdown of files and their exported symbols.
  3. Design tokens, interface contracts, and dependencies.
  4. Maintenance guidelines and testing instructions.

### 5.6 Gatekeeper Merge Discipline
- Feature branches (`backend/*`, `frontend/*`, `ux/*`) must **never** be merged directly into `main` or `develop` by their authoring agents.
- When an author completes a feature branch, it hands the branch off to the Testing Gatekeeper (`agy100`–`agy150`).
- The Testing Gatekeeper verifies 100% passing tests and validates visual fidelity before executing the merge into `develop`.
- Final release promotion from `develop` into `main` is executed exclusively by the Lead Orchestrator (`agy1`).

---

## 6. Authentication, Quota Tracking & Multi-Account Isolation

### 6.1 Multi-Account Token Vault
To allow 200 agents to operate concurrently without hitting single-account concurrency limits or clobbering OAuth refresh tokens:
- Central tokens are stored securely under `~/.gemini/tokens/agy<N>.token` with strict permissions (`chmod 0600`).
- Each instance directory maintains its synchronized local `token.json`.
- A cross-process file lock (`~/.gemini/tokens/.credential.lock`) prevents race conditions whenever an agent refreshes its session tokens.

### 6.2 Collective Quota Dashboard (`agys -u`)
The built-in quota monitoring engine parses session headers, token expiration timestamps, and API response quotas across all slots, rendering an interactive terminal dashboard:

```
=============================================================================================================
                                 AGY Multi-Instance Collective Quota & Usage                                 
=============================================================================================================
 INSTANCE   | ACCOUNT / EMAIL              | STATUS       | 5-HOUR LIMIT (BAR)               | WEEKLY LIMIT (BAR)              
-------------------------------------------------------------------------------------------------------------
 agy1       | account-alpha@example.com    | Active       | [████████████████████] 100% 4h52m | [██████████████████░░] 91% 6d12h
 agy11      | account-beta@example.com     | Active       | [██████████████░░░░░░]  72% 2h14m | [██████████████░░░░░░] 74% 4d08h
 agy51      | account-gamma@example.com    | Low Quota    | [█████░░░░░░░░░░░░░░░]  28% 0h45m | [██████████░░░░░░░░░░] 52% 3d02h
 agy100     | account-delta@example.com    | Active       | [██████████████████░░]  94% 4h30m | [██████████████████░░] 90% 5d18h
=============================================================================================================
 Total Instances: 28  |  Active Accounts: 24  |  Logged Out: 4
=============================================================================================================
```

---

## 7. Compiling & Operating the Native Rust Engine (`agi`)

The core orchestration TUI is located in [`tui-core/`](file:///home/pluto/projects/mind/tui-core/) and compiles into the standalone high-performance binary `agi`.

### 7.1 Compilation

Compile the release binary with compiler optimizations:

```bash
# Navigate to the Rust core directory
cd tui-core

# Check compilation integrity
cargo check

# Build optimized release binary
cargo build --release

# The compiled binary is available at:
# tui-core/target/release/agi
```

### 7.2 Launching the Orchestrator

```bash
# Launch interactive TUI multiplexer
./target/release/agi

# Or run directly via Cargo
cargo run --release --bin agi
```

### 7.3 Navigation & Modal Controls

The compiled TUI features a Tokyo Night dual-pane layout with Vim-style modal navigation:
- **Left Pane**: Dedicated Primary Coordinator terminal (`agy1`).
- **Right Pane**: Interactive Worker Tab Multiplexer (`agy2` .. `agyN`).

| Mode / Key | Action |
|---|---|
| **`NORMAL Mode`** | Default command mode for navigation and window management. |
| `i`, `Enter`, `a` | Enter **`PTY_INTERACT`** mode to send raw keystrokes directly to the focused agent terminal. |
| `Tab` / `Shift+Tab` | Toggle active focus between the Primary Coordinator and the Worker pane. |
| `1` .. `9` | Fast jump directly to Worker Tab #1 through Tab #9. |
| `c` | Create / open a new worker tab. |
| `x` | Close the currently focused worker tab. |
| `w` | Open the **Worker Slot Selector Modal** (`agy1`..`agy200`) with live search. |
| `?` | Toggle the quick-reference Help Modal. |
| **`PTY_INTERACT Mode`** | Passes all scancodes and characters directly to the active child pseudoterminal. |
| `Ctrl+B`, `F12`, `Esc Esc` | Instantly exit `PTY_INTERACT` mode and return to `NORMAL` mode. |

---

## 8. Verification & Troubleshooting

### 8.1 Bubblewrap Permission Denied
If executing `agys` produces `bwrap: setting up uid map: Permission denied`:
```bash
# Verify SUID bit or enable unprivileged user namespaces
sudo chmod u+s $(which bwrap)
# Or
sudo sysctl -w kernel.unprivileged_userns_clone=1
```

### 8.2 X11 Display Authorization for Visual Verification
If `agy100` visual regression tests cannot connect to the display:
```bash
# Ensure DISPLAY and XAUTHORITY are exported
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
xhost +SI:localuser:$USER
```

### 8.3 Resynchronizing Directives
If agent principles or role files are updated, synchronize all existing instances:
```bash
agys --sync
```
This updates `.gemini/GEMINI.md`, refreshes aliases, and ensures all slots operate under the latest governance policies.
