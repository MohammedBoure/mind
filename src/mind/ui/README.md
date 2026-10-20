# `src/mind/ui/` — UI Components & Screens

This directory contains all Textual-based UI widgets and screens for the `mind` TUI multiplexer.

## Files

| File | Description |
|---|---|
| `__init__.py` | Package init for the UI module. |
| `styles.tcss` | Global Textual stylesheet featuring a high-contrast Tokyo Night / Zellij palette with modal and tab bar styling. |
| `session_picker.py` | Landing screen showing active sessions with selection, creation, and keyboard navigation. |
| `new_session_modal.py` | Modal dialog for creating a new session (name, agent count, goal). |
| `workspace.py` | Main multiplexer workspace screen. Mounts live interactive PTY terminal session for Primary Coordinator (`agy1.cmd`) in left pane (`#primary-pane`) with MCP orchestration prompt, handles seamless `Tab` focus switching between Coordinator and Workers, Vim modal system, visible tab bar, split-view toggling ('s'), and MCP lifecycle. |
| `terminal_tab.py` | Interactive terminal components: `TerminalScreenWidget`, `WorkerTerminalTab` (with Primary Coordinator role styling, instance identity & runtime CLI warnings), and `WorkerTabBar` (unclipped full-Unicode tab titles). |
| `agent_config_modal.py` | Interactive Agent Configuration & Discovery Modal (`AgentConfigModal`): dynamically discovers installed system agents (`agy1`, `agy2`, etc.), assigns `--agent <name>`, tunes CLI flags (`--mode`, `--model`, `--effort`), and updates tabs in real time. |
| `directive_modal.py` | Agent Assignment & Task Dispatcher modal (`DirectiveModal`): select agent (Primary Coordinator or Worker 1..N), assign role, and dispatch prompt or interrupt directly to running PTY processes. |
| `header_bar.py` | Streamlined Zellij-inspired top bar (`HeaderBar`): fixed 1-line dock-top with brand, session, active worker telemetry, and MCP status (mode indicator cleanly centralized in bottom bar). |
| `bottom_bar.py` | Multi-segment status bar (`BottomBar`): fixed 1-line dock-bottom with dynamic action pills and PTY platform status. |
| `agent_pane.py` | Agent log pane widget — scrollable, color-coded log stream for the Primary coordinator. |
| `interrupt_banner.py` | Visual toast alert banner for inter-agent message interruptions and directives. |
| `help_modal.py` | Help modal overlay showing the complete Vim modal navigation, tab controls, and shortcuts. |
