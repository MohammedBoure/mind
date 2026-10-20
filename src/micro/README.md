# `src/micro/` — Root Package

This is the root Python package for the **mind · micro** TUI application.

## Files

| File | Description |
|---|---|
| `__init__.py` | Package init with version metadata. |
| `app.py` | Main `MicroApp` (Textual `App` subclass) — screen routing and event handling. |
| `events.py` | Custom Textual messages for decoupled UI ↔ backend communication. |

## Subdirectories

| Directory | Description |
|---|---|
| `cli/` | Click CLI entrypoint (`micro` command and `micro new` subcommand). |
| `state/` | Domain models, enums, and mock data providers. |
| `ui/` | All Textual widgets, screens, modals, and the global stylesheet. |
