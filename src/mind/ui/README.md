# `src/mind/ui/` — UI Components & Screens

This directory contains all Textual-based UI widgets and screens for the `mind` TUI multiplexer.

## Files

| File | Description |
|---|---|
| `__init__.py` | Package init for the UI module. |
| `styles.tcss` | Global Textual stylesheet featuring a high-contrast Tokyo Night / Zellij palette. |
| `session_picker.py` | Landing screen showing active sessions with selection, creation, and keyboard navigation. |
| `new_session_modal.py` | Modal dialog for creating a new session (name, agent count, goal). |
| `workspace.py` | Main multiplexer workspace screen with side-by-side coordinator/worker panes, focus routing, and MCP lifecycle. |
| `terminal_tab.py` | Interactive ANSI terminal screen (`TerminalScreenWidget`) with placeholder banner and worker container (`WorkerTerminalTab`). |
| `directive_modal.py` | Interactive modal (`DirectiveModal`) for injecting targeted inter-agent directives and interrupts via `Ctrl+M`. |
| `header_bar.py` | Streamlined Zellij-inspired top bar: `mind` branding, active session pill, interactive mode badge, and MCP status. |
| `bottom_bar.py` | Multi-segment status bar with clickable action pills (`Alt+1..N`, `Tab`, `Ctrl+M`, `Ctrl+C`, `?`, `q`) and PTY backend indicator. |
| `agent_pane.py` | Agent log pane widget — scrollable, color-coded log stream for the Primary coordinator. |
| `interrupt_banner.py` | Visual toast alert banner for inter-agent message interruptions and directives. |
| `help_modal.py` | Help modal overlay showing all keyboard shortcuts and architecture navigation. |
