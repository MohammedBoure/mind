# `src/mind/ui/` — UI Components & Screens

This directory contains all Textual-based UI widgets and screens for the `mind` TUI multiplexer.

## Files

| File | Description |
|---|---|
| `__init__.py` | Package init for the UI module. |
| `styles.tcss` | Global Textual stylesheet featuring a high-contrast Tokyo Night / Zellij palette with modal and tab bar styling. |
| `session_picker.py` | Landing screen showing active sessions with selection, creation, and keyboard navigation. |
| `new_session_modal.py` | Modal dialog for creating a new session (name, agent count, goal). |
| `workspace.py` | Main multiplexer workspace screen implementing Vim Modal System, visible tab bar, split-view toggling ('s'), and MCP lifecycle. |
| `terminal_tab.py` | Interactive terminal components: `TerminalScreenWidget`, `WorkerTerminalTab`, clickable `WorkerTabPill`, `WorkerNewTabPill`, and `WorkerTabBar`. |
| `directive_modal.py` | Agent Assignment & Task Dispatcher modal (`DirectiveModal`): select agent (Primary or Worker 1..N), assign role, and dispatch prompt to agy.exe. |
| `header_bar.py` | Streamlined Zellij-inspired top bar (`HeaderBar`): fixed 1-line dock-top with brand, session, Vim mode badge, and MCP status. |
| `bottom_bar.py` | Multi-segment status bar (`BottomBar`): fixed 1-line dock-bottom with dynamic action pills and PTY platform status. |
| `agent_pane.py` | Agent log pane widget — scrollable, color-coded log stream for the Primary coordinator. |
| `interrupt_banner.py` | Visual toast alert banner for inter-agent message interruptions and directives. |
| `help_modal.py` | Help modal overlay showing the complete Vim modal navigation, tab controls, and shortcuts. |
