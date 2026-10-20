# mind

> **AI Multi-Agent Orchestration TUI** — A terminal user interface for managing and monitoring multi-agent AI sessions within the *mind* system.

---

## Features

- **Session Picker** — Browse, create, and select agent sessions from a centralized picker screen.
- **Multi-Agent Workspace** — Real-time dashboard showing all agents in a session: their status, roles, and live log streams.
- **Agent Log Streams** — Follow each agent's chain-of-thought, tool calls, and results as they happen.
- **Inter-Agent Messaging** — Inject directives and interrupt agents with prioritized messages.
- **Keyboard-Driven** — Full keyboard navigation for power users; no mouse required.

## Installation

```bash
# Using pip (editable / dev mode)
pip install -e .

# Using uv
uv pip install -e .
```

## Usage

```bash
# Launch the session picker (default)
mind

# Create and enter a new session directly
mind new <session_name>
```

### Key Bindings

| Key          | Action                          |
|--------------|---------------------------------|
| `q`          | Quit the application            |
| `n`          | New session (from picker)       |
| `Enter`      | Select / confirm                |
| `Tab`        | Cycle focus between panels      |
| `↑` / `↓`   | Navigate lists                  |
| `i`          | Open interrupt / directive input|
| `?`          | Toggle help overlay             |

## Architecture

```
src/micro/
├── cli/            # Click CLI entrypoint
│   └── main.py     # `micro` command group
├── state/          # Domain models & data layer
│   ├── models.py   # Dataclass models (Agent, Session, Log, etc.)
│   └── mock_data.py# Mock data provider (placeholder for real backend)
├── events.py       # Custom Textual messages for UI-backend decoupling
└── app.py          # Textual Application class (entry point for TUI)
```

The project follows a strict **separation of concerns**:

1. **CLI layer** (`cli/`) — Parses commands and boots the Textual app.
2. **State layer** (`state/`) — Domain models, data access, and mock data.
3. **Events** (`events.py`) — Custom Textual `Message` subclasses that decouple the UI from the backend.
4. **UI layer** — Textual screens, widgets, and the main `App` class.

## Development

```bash
# Install in editable mode with dev dependencies
pip install -e .

# Run the TUI
micro

# Run with Textual dev tools
textual run --dev -c micro
```

## License

MIT
