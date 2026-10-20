# `src/mind/ui/` — UI Components

This directory contains all Textual-based UI widgets and screens for the `mind` TUI.

## Files

| File | Description |
|---|---|
| `__init__.py` | Package init for the UI module. |
| `styles.tcss` | Global Textual CSS stylesheet (Zellij-inspired theme with terminal emulator styles). |
| `session_picker.py` | Landing screen showing active sessions with selection and creation. |
| `new_session_modal.py` | Modal dialog for creating a new session (name, agent count, goal). |
| `workspace.py` | Main workspace screen with split-pane layout, interactive worker PTYs, and MCP bridge. |
| `terminal_tab.py` | Worker tab component with interactive ANSI terminal screen, status line, and MCP toast banners. |
| `header_bar.py` | Top bar widget: session badge, status indicator, and agent tabs. |
| `bottom_bar.py` | Bottom bar widget displaying keyboard shortcut hints. |
| `agent_pane.py` | Agent log pane widget — scrollable, color-coded log stream for Primary coordinator. |
| `interrupt_banner.py` | Visual alert banner for inter-agent message interrupts. |
| `help_modal.py` | Help modal overlay showing all keyboard shortcuts. |
