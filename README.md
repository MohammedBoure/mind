# mind

> **AI Multi-Agent Orchestration TUI** — A high-performance terminal user interface and MCP bridge for managing, monitoring, and steering multi-agent AI sessions running `agy` CLI agents.

---

## Features

- **Session Picker** — Browse, create, and launch agent workspaces interactively.
- **PTY Terminal Multiplexing** — Each worker tab runs a real, interactive terminal session running `agy` (on Windows via `pywinpty` / ConPTY, on Unix/Linux via `ptyprocess` / `termios`).
- **Virtual Screen Emulation** — In-memory, thread-safe 2D character matrix and ring buffer powered by `pyte` and `rich`.
- **Embedded MCP Server (`mind-mcp`)** — Background FastMCP server exposing tools to the primary coordinator agent:
  - `list_workers()`: Inspect active worker tabs, agent IDs, and process states.
  - `get_terminal_screen(worker_id, lines)`: Read rendered ANSI/clean text from any worker terminal.
  - `send_terminal_input(worker_id, text, press_enter)`: Send raw input/commands to worker stdin.
  - `interrupt_and_inject(worker_id, sender_id, message, priority)`: Send SIGINT / Ctrl+C to pause ongoing agent actions, wait for prompt to settle, and inject formatted directives.
  - `get_agent_profile(agent_id)`: Query agent role, principles, instructions, and `./agent` config.
- **Direct Interactive Control** — Switch tabs, click into any worker terminal, and type directly into `agy` at any time.
- **Instant Visual Feedback** — MCP-injected directives immediately trigger visual toast badges and alert banners in the TUI.

---

## Installation

### Development Mode (Editable Install)

Install `mind` in editable mode using `pip`:

```bash
# Basic installation
pip install -e .

# Or including test dependencies (pytest, pytest-asyncio, anyio)
pip install -e ".[test]"
```

Or using `uv`:

```bash
uv pip install -e .
```

After installation, the CLI entrypoint `mind` becomes available system-wide (defined via `project.scripts` in [`pyproject.toml`](file:///C:/Users/moham/Desktop/mind/pyproject.toml)).

---

## Usage

```bash
# Launch the session picker
mind

# Directly create and enter a new session
mind new my_task

# Run the MCP server over stdio (for stdio-based MCP clients)
mind mcp

# Automatically register the mind-mcp server with agy
mind register-mcp --transport sse --port 8765

# Inspect multi-account quota and consumption table
mind usage
mind -u

# Export quota usage statistics as JSON
mind usage --json
```

---

## Connecting the Primary Agent to `mind-mcp`

When `mind` launches a workspace, it boots the embedded MCP server in the background at:
```
http://127.0.0.1:8765/sse
```

To enable the primary coordinator agent running in `agy` to use `mind-mcp` tools, register it once:
```bash
agy mcp add mind-mcp http://127.0.0.1:8765/sse
```
Or run the built-in helper:
```bash
mind register-mcp
```

---

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `q` | Quit the application |
| `?` | Toggle keyboard shortcuts modal |
| `Alt+1`..`Alt+5` | Fast tab switching to Worker N |
| `Tab` / `Shift+Tab` | Cycle focus between panes |
| `Click` inside terminal | Focus worker terminal and type directly |
| `Ctrl+C` | Send interrupt signal to active terminal process |
| `m` | Trigger mock interrupt directive injection test |
| `s` | Toggle split layout (side-by-side ↔ stacked) |
| `n` | Add new worker agent tab dynamically |
| `Escape` | Go back / dismiss modals |

---

## Architecture & Directory Structure

`mind` is designed as a modular, cross-platform architecture supporting both Windows (ConPTY) and POSIX/Linux platforms:

```
mind/
├── docs/                       # Technical architecture & specification documents
├── pyproject.toml              # Build configuration, entrypoint scripts, and dependencies
├── README.md                   # Project overview & documentation
├── tasks.md                    # Roadmap & transformation plan
├── scripts/                    # QA and integration scripts
├── tests/                      # Automated test suite (pytest, anyio)
└── src/
    └── mind/                   # Root Python package
        ├── app.py              # Root Textual App & screen lifecycle
        ├── events.py           # Custom Textual messages
        ├── cli/                # Command-line interface definitions
        ├── core/               # PTY multiplexing, auth, buffer, and process orchestration
        │   └── auth/           # Modular authentication, token validation & keyring backends
        ├── mcp/                # Embedded Model Context Protocol server & runners
        ├── state/              # Domain models, dataclasses, and mock state
        └── ui/                 # Textual widgets, screens, styles, and modals
```

### Primary Package Modules

| Directory / File | Description & Purpose |
|---|---|
| [`pyproject.toml`](file:///C:/Users/moham/Desktop/mind/pyproject.toml) | Package metadata, build system configuration (Hatchling), CLI entrypoints (`mind = "mind.cli.main:main"`), cross-platform dependencies, and pytest configuration with `pythonpath = ["src"]`. |
| [`src/mind/app.py`](file:///C:/Users/moham/Desktop/mind/src/mind/app.py) | Main application class (`MindApp`) managing screens and top-level lifecycle. |
| [`src/mind/events.py`](file:///C:/Users/moham/Desktop/mind/src/mind/events.py) | Decoupled Textual event definitions for UI messaging. |
| [`src/mind/cli/`](file:///C:/Users/moham/Desktop/mind/src/mind/cli/) | Click-based CLI entrypoints implementing `mind`, `mind new`, `mind mcp`, and `mind register-mcp`. |
| [`src/mind/core/`](file:///C:/Users/moham/Desktop/mind/src/mind/core/) | Core infrastructure including pseudoterminal abstraction (`BasePtyProcess`), virtual terminal buffer (`TerminalBuffer`), agent discovery, directives hot-reloading, and terminal manager orchestrator. |
| [`src/mind/core/auth/`](file:///C:/Users/moham/Desktop/mind/src/mind/core/auth/) | Modular authentication system: BOM sanitization, token claim extraction, Windows Credential Manager & POSIX keyrings, mutex synchronization, and slot isolation. |
| [`src/mind/mcp/`](file:///C:/Users/moham/Desktop/mind/src/mind/mcp/) | Embedded Model Context Protocol (MCP) server providing coordinator agent control tools via SSE and Stdio transports. |
| [`src/mind/state/`](file:///C:/Users/moham/Desktop/mind/src/mind/state/) | Operational domain models, agent metadata, and state definitions. |
| [`src/mind/ui/`](file:///C:/Users/moham/Desktop/mind/src/mind/ui/) | Complete Textual user interface: Tokyo Night styling (`styles.tcss`), Vim-mode workspace multiplexer, interactive PTY terminal widget, and modal dialogs. |
| [`tests/`](file:///C:/Users/moham/Desktop/mind/tests/) | Full test suite covering auth isolation, directives, PTY multiplexing, MCP tools, and Vim navigation. |
| [`docs/`](file:///C:/Users/moham/Desktop/mind/docs/) | In-depth technical specifications and architectural documentation. |

---

## Cross-Platform PTY Abstraction

`mind` supports seamless execution across Windows and Linux/POSIX environments:

1. **Windows:**
   - Employs Windows Pseudo Console (`ConPTY`) via `pywinpty`.
   - Manages console handles, input scancodes, and UTF-8 escape sequences.
2. **Linux & POSIX:**
   - Employs native POSIX pseudo-terminals via `openpty`, `ptyprocess`, and the Python standard library `termios`.
   - Full support for POSIX signals (`SIGINT`, `SIGTERM`, `SIGHUP`).
3. **Process Safety:**
   - Cross-platform process monitoring and zombie process prevention via `psutil`.

---

## Testing

The project uses `pytest` with `pytest-asyncio` and `anyio` for asynchronous testing in headless mode:

```bash
# Run the entire test suite
pytest

# Run tests with verbose output
pytest -v

# Run a specific test module
pytest tests/test_vim_modal.py
```

The import path `pythonpath = ["src"]` configured in [`pyproject.toml`](file:///C:/Users/moham/Desktop/mind/pyproject.toml) ensures the package is resolved directly from source during testing.

---

## License

MIT
