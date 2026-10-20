# `src/mind/ui/` — UI Components & Screens

This directory contains all Textual-based UI widgets and screens for the `mind` TUI multiplexer.

## Files

| File | Description |
|---|---|
| `__init__.py` | Package init for the UI module. |
| `styles.tcss` | Global Textual stylesheet featuring a high-contrast Tokyo Night / Zellij palette with modal styling. |
| `session_picker.py` | Landing screen showing active sessions with selection, creation, and keyboard navigation. |
| `new_session_modal.py` | Modal dialog for creating a new session (name, agent count, goal). |
| `workspace.py` | Main multiplexer workspace screen implementing the Vim Modal System (NORMAL vs PTY_INTERACT), focus routing, and MCP lifecycle. |
| `terminal_tab.py` | Interactive ANSI terminal screen (`TerminalScreenWidget`) with Vim modal input interception and worker container (`WorkerTerminalTab`). |
| `directive_modal.py` | Interactive modal (`DirectiveModal`) for injecting targeted inter-agent directives and interrupts via `Ctrl+M` or `m`. |
| `header_bar.py` | Streamlined Zellij-inspired top bar: `mind` branding, active session pill, dynamic Vim mode badge, and MCP status. |
| `bottom_bar.py` | Multi-segment status bar dynamically toggling between NORMAL command pills and PTY action pills, plus PTY platform status. |
| `agent_pane.py` | Agent log pane widget — scrollable, color-coded log stream for the Primary coordinator. |
| `interrupt_banner.py` | Visual toast alert banner for inter-agent message interruptions and directives. |
| `help_modal.py` | Help modal overlay showing the complete Vim modal navigation, tab controls, and shortcuts. |
