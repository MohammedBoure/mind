# `src/mind/` — Root Package

This is the root Python package for the **mind** AI Multi-Agent Orchestration system.

## Files

| File | Description |
|---|---|
| `__init__.py` | Package init with version metadata. |
| `app.py` | Main `MindApp` (Textual `App` subclass) — screen routing and event handling. |
| `events.py` | Custom Textual messages for decoupled UI ↔ backend communication. |

## Subdirectories

| Directory | Description |
|---|---|
| `cli/` | Click CLI entrypoints (`mind`, `new`, `usage`, `doctor`, `sessions`, `mcp`, `register-mcp`). |
| `core/` | Pseudoterminal multiplexing, virtual screen buffers, multi-slot auth isolation, process lifecycles, and usage monitor. |
| `mcp/` | Embedded Model Context Protocol server exposing tools to coordinator agents. |
| `state/` | Domain models, enums, dataclasses, and mock data providers. |
| `ui/` | All Textual widgets, terminal screens, Vim modal workspace, 5-tier clipboard engine, modals, and the global stylesheet. |
