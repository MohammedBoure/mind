# mind

> **AI Multi-Agent Orchestration TUI** — A high-performance terminal user interface and MCP bridge for managing, monitoring, and steering multi-agent AI sessions running `agy` CLI agents.

---

## Features

- **Session Picker** — Browse, create, and launch agent workspaces interactively.
- **PTY Terminal Multiplexing** — Each worker tab runs a real, interactive terminal session running `agy` (on Windows via `pywinpty` / ConPTY, on Unix via `pty`/`termios`).
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

```bash
# Using pip (editable / dev mode)
pip install -e .

# Or using uv
uv pip install -e .
```

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

## Architecture

```
aze/
├── docs/                       # Technical architecture & specification documents
├── pyproject.toml              # Build config, scripts (`mind`), dependencies
├── README.md                   # Project overview & documentation
└── src/mind/
    ├── app.py                  # Root Textual App & screen lifecycle
    ├── events.py               # Custom Textual messages
    ├── cli/
    │   └── main.py             # Click CLI (`mind`, `new`, `mcp`, `register-mcp`)
    ├── core/
    │   ├── pty_process.py      # Cross-platform PTY spawner (winpty/Unix) with zombie safety
    │   ├── credentials.py      # Cross-process credential & slot isolation management
    │   ├── terminal_buffer.py  # pyte 2D virtual screen, ring buffer & Rich renderer
    │   └── terminal_manager.py # WorkerSession & TerminalManager orchestrator
    ├── mcp/
    │   ├── server.py           # FastMCP tools (list, screen, input, interrupt, profile)
    │   └── runner.py           # Background HTTP/SSE runner & stdio runner
    ├── state/
    │   ├── models.py           # Dataclasses & operational enums
    │   └── mock_data.py        # Seed sessions and primary coordinator stream
    └── ui/
        ├── styles.tcss         # Zellij-inspired terminal multiplexer stylesheet
        ├── workspace.py        # Multiplexer workspace screen with split panes
        ├── terminal_tab.py     # Interactive PTY terminal widget with toast alerts
        ├── header_bar.py       # Top session status bar and agent tabs
        ├── bottom_bar.py       # Bottom keybinds helper bar
        ├── interrupt_banner.py # Visual alert banner for inter-agent messages
        ├── session_picker.py   # Session picker screen
        ├── new_session_modal.py# Session creation dialog
        └── help_modal.py       # Shortcuts overlay
```

---

## License

MIT
