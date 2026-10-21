# `src/mind/ui/` — UI Components & Screens

This directory contains all Textual-based UI widgets and screens for the `mind` TUI multiplexer.

## Files

| File | Description |
|---|---|
| `__init__.py` | Package init for the UI module. |
| `styles.tcss` | Global Textual stylesheet featuring a high-contrast Tokyo Night palette (deep indigo/slate canvases, vibrant accents), Zellij/Helix-inspired header and status bars, soft rounded borders (`border: round`), smart visual separation between Coordinator and Worker panes, and full compatibility with developer monospace fonts, Nerd Fonts, Unicode, and Arabic characters. |
| `session_picker.py` | Landing screen showing active sessions with selection, creation, and keyboard navigation. |
| `new_session_modal.py` | Modal dialog for creating a new session (name, agent count, goal). |
| `clipboard.py` | Cross-platform OS clipboard synchronization utility (`copy_to_clipboard`, `get_clipboard_text`) integrating `pyperclip` with Textual `app.copy_to_clipboard`. |
| `workspace.py` | Main multiplexer workspace screen featuring a high-precision dual Vim modal system: **NORMAL Mode** (instant single-key command dispatch: `1..9` tab jumping, `h/l` cycling, `s` split-view toggling and full-screen expansion, `m` directive injection modal, `e` agent configuration modal, `c` new worker tab, `x` tab termination, `y` clipboard yank, `d` in-app directive editor, `o` external editor, `q` quit, `?` help, `Tab` pane focus cycling) and **PTY_INTERACT Mode** (zero-delay raw stdin passthrough with instantaneous Leader exits via `Ctrl+B`, `F12`, or `Esc Esc` double escape within 350ms, while preserving bare single Escape for internal child Vim prompts). Features flexible Split View (permanent Primary Coordinator `#primary-pane` on left, interactive Worker tab switcher `#workers-pane` on right with focus-aware full-screen expansion), Lazy Spawning (launching only Coordinator and initial Worker at boot, auto-spawning subsequent workers on tab activation), directive hot-reload sync with visual toasts, and non-blocking MCP lifecycle management. |
| `terminal_tab.py` | Interactive terminal components: `TerminalScreenWidget` (with visibility-aware rendering, event-driven output updates, mouse selection auto-copy, right-click copy, shortcut triggers `Ctrl+M`, `Ctrl+E`, `Ctrl+O`, `Ctrl+D`, and Vim-over-Vim escape passthrough), `WorkerTerminalTab` (with Primary Coordinator role styling, instance identity & runtime CLI warnings), and `WorkerTabBar` (unclipped full-Unicode tab titles). |
| `agent_config_modal.py` | Interactive Agent Configuration & Discovery Modal (`AgentConfigModal`): dynamically discovers installed system agents (`agy1`, `agy2`, etc.), assigns `--agent <name>`, tunes CLI flags (`--mode`, `--model`, `--effort`), provides in-app and external directive management, and updates tabs in real time. |
| `directive_editor_modal.py` | In-app modal text editor (`DirectiveEditorModal`) for inspecting, modifying, and saving agent behavioral Markdown guidelines directly within the TUI. Supports `Ctrl+S` (Save & apply), `Ctrl+O` (Open in system default editor), and `Esc` (Cancel). |
| `directive_modal.py` | Agent Assignment & Task Dispatcher modal (`DirectiveModal`): select agent (Primary Coordinator or Worker 1..N), assign role, and dispatch prompt or interrupt directly to running PTY processes. |
| `header_bar.py` | Streamlined Zellij-inspired top bar (`HeaderBar`): fixed 1-line dock-top with brand, session, active worker telemetry, and MCP status (mode indicator cleanly centralized in bottom bar). |
| `bottom_bar.py` | Multi-segment status bar (`BottomBar`): fixed 1-line dock-bottom with dynamic action pills (including yank/copy, directive editor `d/o` / `Ctrl+D/O`, and Esc Esc / Ctrl+B indicator) and PTY platform status. |
| `agent_pane.py` | Agent log pane widget — scrollable, color-coded log stream for agents with mouse click / right-click clipboard copying. |
| `interrupt_banner.py` | Visual toast alert banner for inter-agent message interruptions and directives. |
| `help_modal.py` | Help modal overlay showing the complete Vim modal navigation, tab controls, external & in-app directive shortcuts (`o / Ctrl+O`, `d / Ctrl+D`), and general keybindings. |
