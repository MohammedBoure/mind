"""Interactive in-app Agent Configuration & Settings Modal (Antigravity CLI Style).

Implements a pure keyboard-driven, two-column interactive configuration menu
matching the Antigravity CLI / Codex config layout:
- Real-time search filter at the top (`Search: `)
- Two-column interactive settings list with `>` cursor indicator
- Instant option cycling via Left/Right, Space, or Enter
- Dynamic bottom description explaining the currently selected setting
- Full keyboard navigation (Up/Down/j/k, Left/Right/h/l, /, Backspace, Ctrl+R, Esc)
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Callable

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Input, Static, TextArea

from mind.core.agent_discovery import discover_system_agents, get_agent_preset_config
from mind.core.directives import (
    ensure_default_directives,
    get_worker_directive_path,
    load_directive,
    open_directive_in_editor,
    resolve_directive_path,
    save_directive,
)
from mind.core.terminal_manager import TerminalManager
from mind.ui.directive_editor_modal import DirectiveEditorModal


@dataclass
class ConfigOption:
    """Represents a single configuration setting entry with interactive options."""
    key: str
    label: str
    options: list[str]
    current_index: int = 0
    description: str = ""
    is_worker_specific: bool = False

    @property
    def value(self) -> str:
        if not self.options:
            return ""
        return self.options[self.current_index % len(self.options)]

    def cycle_next(self) -> str:
        if self.options:
            self.current_index = (self.current_index + 1) % len(self.options)
        return self.value

    def cycle_prev(self) -> str:
        if self.options:
            self.current_index = (self.current_index - 1) % len(self.options)
        return self.value

    def set_value(self, val: str) -> None:
        if val in self.options:
            self.current_index = self.options.index(val)
        elif self.options:
            # Custom or fuzzy match
            for i, opt in enumerate(self.options):
                if opt.lower() == val.lower():
                    self.current_index = i
                    return
            # If not in options, append as custom option and select it
            self.options.append(val)
            self.current_index = len(self.options) - 1


class ConfigSettingsListWidget(Widget):
    """Interactive, keyboard-driven two-column settings list with cursor and scrolling."""

    can_focus = True

    def __init__(
        self,
        entries: list[ConfigOption],
        on_change: Callable[[ConfigOption], None] | None = None,
        on_selection_change: Callable[[ConfigOption | None], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.entries = entries
        self._on_change = on_change
        self._on_selection_change = on_selection_change
        self.selected_index: int = 0
        self.view_scroll_offset: int = 0
        self.search_query: str = ""

    def get_filtered_entries(self) -> list[tuple[int, ConfigOption]]:
        """Return list of (original_index, entry) matching current search query."""
        if not self.search_query.strip():
            return list(enumerate(self.entries))
        q = self.search_query.lower()
        return [
            (i, entry)
            for i, entry in enumerate(self.entries)
            if q in entry.label.lower() or q in entry.key.lower() or q in entry.value.lower()
        ]

    def get_active_entry(self) -> ConfigOption | None:
        """Get currently highlighted entry."""
        filtered = self.get_filtered_entries()
        if not filtered:
            return None
        safe_idx = max(0, min(self.selected_index, len(filtered) - 1))
        return filtered[safe_idx][1]

    def set_search_query(self, query: str) -> None:
        """Update search query and adjust selection."""
        self.search_query = query
        self.selected_index = 0
        self.view_scroll_offset = 0
        self.refresh()
        self._notify_selection_changed()

    def _notify_selection_changed(self) -> None:
        if self._on_selection_change:
            self._on_selection_change(self.get_active_entry())

    def action_move_up(self) -> None:
        """Move cursor up."""
        filtered = self.get_filtered_entries()
        if not filtered:
            return
        if self.selected_index > 0:
            self.selected_index -= 1
            if self.selected_index < self.view_scroll_offset:
                self.view_scroll_offset = self.selected_index
            self.refresh()
            self._notify_selection_changed()

    def action_move_down(self) -> None:
        """Move cursor down."""
        filtered = self.get_filtered_entries()
        if not filtered:
            return
        if self.selected_index < len(filtered) - 1:
            self.selected_index += 1
            visible_rows = max(1, self.size.height or 16)
            if self.selected_index >= self.view_scroll_offset + visible_rows:
                self.view_scroll_offset = self.selected_index - visible_rows + 1
            self.refresh()
            self._notify_selection_changed()

    def action_cycle_next(self) -> None:
        """Cycle current setting option forward."""
        entry = self.get_active_entry()
        if entry:
            entry.cycle_next()
            self.refresh()
            if self._on_change:
                self._on_change(entry)
            self._notify_selection_changed()

    def action_cycle_prev(self) -> None:
        """Cycle current setting option backward."""
        entry = self.get_active_entry()
        if entry:
            entry.cycle_prev()
            self.refresh()
            if self._on_change:
                self._on_change(entry)
            self._notify_selection_changed()

    def on_key(self, event: events.Key) -> None:
        """Handle keyboard navigation and option toggling."""
        key = event.key
        char = event.character or ""

        if key in ("up", "k"):
            self.action_move_up()
            event.stop()
            event.prevent_default()
        elif key in ("down", "j"):
            self.action_move_down()
            event.stop()
            event.prevent_default()
        elif key in ("right", "l", "space", "enter"):
            self.action_cycle_next()
            event.stop()
            event.prevent_default()
        elif key in ("left", "h"):
            self.action_cycle_prev()
            event.stop()
            event.prevent_default()
        elif key == "pageup":
            for _ in range(5):
                self.action_move_up()
            event.stop()
            event.prevent_default()
        elif key == "pagedown":
            for _ in range(5):
                self.action_move_down()
            event.stop()
            event.prevent_default()
        elif key == "home":
            self.selected_index = 0
            self.view_scroll_offset = 0
            self.refresh()
            self._notify_selection_changed()
            event.stop()
            event.prevent_default()
        elif key == "end":
            filtered = self.get_filtered_entries()
            if filtered:
                self.selected_index = len(filtered) - 1
                visible_rows = max(1, self.size.height or 16)
                self.view_scroll_offset = max(0, len(filtered) - visible_rows)
                self.refresh()
                self._notify_selection_changed()
            event.stop()
            event.prevent_default()
        elif key == "slash":
            # Focus search input on '/'
            try:
                inp = self.screen.query_one("#config-search-input", Input)
                inp.focus()
            except Exception:
                pass
            event.stop()
            event.prevent_default()

    def on_mouse_down(self, event: events.MouseDown) -> None:
        """Click to select row or cycle value."""
        self.focus()
        clicked_row = event.y + self.view_scroll_offset
        filtered = self.get_filtered_entries()
        if 0 <= clicked_row < len(filtered):
            if self.selected_index == clicked_row:
                self.action_cycle_next()
            else:
                self.selected_index = clicked_row
                self.refresh()
                self._notify_selection_changed()

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        self.action_move_up()

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        self.action_move_down()

    def render(self) -> Text:
        """Render two-column settings list with cursor and colors."""
        filtered = self.get_filtered_entries()
        if not filtered:
            return Text.from_markup("  [dim #565f89]No matching configuration options found.[/]")

        visible_rows = max(1, self.size.height or 16)
        # Ensure selected_index is within bounds
        self.selected_index = max(0, min(self.selected_index, len(filtered) - 1))

        # Adjust scroll offset
        if self.selected_index < self.view_scroll_offset:
            self.view_scroll_offset = self.selected_index
        elif self.selected_index >= self.view_scroll_offset + visible_rows:
            self.view_scroll_offset = self.selected_index - visible_rows + 1

        slice_entries = filtered[self.view_scroll_offset : self.view_scroll_offset + visible_rows]

        out = Text()
        col_width = 33

        for i, (orig_idx, entry) in enumerate(slice_entries):
            current_abs_idx = self.view_scroll_offset + i
            is_selected = current_abs_idx == self.selected_index

            val = entry.value
            val_style = "bold #7dcfff"
            if val == "on":
                val_style = "bold #9ece6a"
            elif val == "off":
                val_style = "dim #565f89"
            elif val in ("accept-edits", "auto", "always proceeds", "always-proceed", "fast"):
                val_style = "bold #7dcfff"
            elif val in ("vim", "colorblind-friendly dark", "tokyo-night"):
                val_style = "#bb9af7"

            label_str = f"{entry.label:<{col_width}}"

            if is_selected:
                out.append("> ", style="bold #7aa2f7")
                out.append(label_str, style="bold #ffffff")
                out.append(" ")
                out.append(val, style=val_style)
            else:
                out.append("  ", style="#565f89")
                out.append(label_str, style="#c0caf5")
                out.append(" ")
                out.append(val, style=val_style)

            if i < len(slice_entries) - 1:
                out.append("\n")

        return out


class AgentConfigModal(ModalScreen[None]):
    """Modal overlay presenting the sleek Antigravity CLI configuration layout."""

    BINDINGS = [
        ("escape", "save_and_close", "Save & Close"),
        ("ctrl+r", "save_and_restart", "Save & Restart Worker"),
        ("ctrl+s", "save_and_close", "Save"),
        ("o", "open_directive_file", "Open Directive File"),
        ("ctrl+o", "open_directive_file", "Open Directive File"),
        ("e", "edit_directive_inline", "Edit Directive In-App"),
    ]

    def __init__(
        self,
        default_target: str | None = None,
        on_save_callback: Callable[[str, dict[str, Any], bool], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._default_target = default_target
        self._on_save_callback = on_save_callback
        self._terminal_manager = TerminalManager.get_instance()
        self._discovered_agents = discover_system_agents()
        self.options: list[ConfigOption] = []
        self._init_options()

    def _init_options(self) -> None:
        """Build full list of configuration options matching the screenshot & active agents."""
        workers = self._terminal_manager.list_workers()

        # 1. Target Worker Tab
        tab_options: list[str] = []
        for w in workers:
            tag = w.assigned_agent or w.name
            if w.role == "coordinator" or str(w.worker_id) in ("coordinator", "primary"):
                tab_options.append(f"Coordinator: {tag} (Slot {w.get_slot_id() or 1})")
            else:
                tab_options.append(f"Tab {w.worker_id}: {tag} (Slot {w.get_slot_id() or w.worker_id})")

        if not tab_options:
            tab_options = ["Coordinator: agy1 (Slot 1)", "Tab 1: agy2 (Slot 2)"]

        # Default tab selection
        target_tab_idx = 0
        if self._default_target:
            for i, opt in enumerate(tab_options):
                if str(self._default_target).lower() in opt.lower():
                    target_tab_idx = i
                    break

        # Discovered agents
        agent_names = list(self._discovered_agents) if self._discovered_agents else ["agy1", "agy2"]
        if "agy1" not in agent_names:
            agent_names.insert(0, "agy1")
        if "agy2" not in agent_names:
            agent_names.insert(1, "agy2")

        # Get current worker settings
        current_worker = None
        if workers:
            if self._default_target:
                for w in workers:
                    if str(w.worker_id) == str(self._default_target):
                        current_worker = w
                        break
            if not current_worker:
                current_worker = workers[0]

        cur_mode = current_worker.cli_mode if current_worker else "accept-edits"
        cur_model = current_worker.model if current_worker else "gemini-3.8-flash-high"
        cur_effort = current_worker.reasoning_effort if current_worker else "high"
        cur_agent = current_worker.assigned_agent if current_worker else "agy1"
        cur_flags = current_worker.extra_flags if current_worker else "--dangerously-skip-permissions"
        if not cur_flags:
            cur_flags = "--dangerously-skip-permissions"

        self.options = [
            ConfigOption(
                key="agent_mode",
                label="Agent Mode",
                options=["accept-edits", "auto", "plan", "default"],
                current_index=0,
                description="'default': standard behavior. 'accept-edits': auto-approve file edits, prompt for commands. 'plan': read-only analysis. 'auto': autonomous execution.",
                is_worker_specific=True,
            ),
            ConfigOption(
                key="animation_speed",
                label="Animation Speed",
                options=["fast", "medium", "slow", "off"],
                current_index=0,
                description="Controls animation frame rate and transition timing for terminal multiplexer UI.",
            ),
            ConfigOption(
                key="artifact_review",
                label="Artifact Review",
                options=["always proceeds", "ask", "never"],
                current_index=0,
                description="Controls execution gating for generated code artifacts and suggested tasks.",
            ),
            ConfigOption(
                key="color_scheme",
                label="Color Scheme",
                options=["colorblind-friendly dark", "tokyo-night", "catppuccin", "monokai", "dark", "light"],
                current_index=0,
                description="Active color palette theme applied to TUI borders, headers, and tabs.",
            ),
            ConfigOption(
                key="picker_grouping",
                label="Conversation Picker Grouping",
                options=["none", "by-date", "by-project", "by-agent"],
                current_index=0,
                description="How conversation sessions are organized in the session picker.",
            ),
            ConfigOption(
                key="copy_on_select",
                label="Copy on Select",
                options=["on", "off"],
                current_index=0,
                description="Automatically synchronize mouse-selected text in terminal buffers directly to OS clipboard.",
            ),
            ConfigOption(
                key="editor",
                label="Editor",
                options=["vim", "nano", "code", "notepad", "emacs"],
                current_index=0,
                description="External editor launched for long prompt editing and file inspections.",
            ),
            ConfigOption(
                key="editor_mode",
                label="Editor Mode",
                options=["vim", "emacs", "default"],
                current_index=0,
                description="Modal keybinding system for outer workspace navigation and terminal passthrough.",
            ),
            ConfigOption(
                key="editor_mode_insert_first",
                label="Editor Mode > Insert First",
                options=["off", "on"],
                current_index=0,
                description="Start terminal sessions in Insert/PTY mode instead of Normal mode by default.",
            ),
            ConfigOption(
                key="enable_telemetry",
                label="Enable Telemetry",
                options=["on", "off"],
                current_index=0,
                description="Send anonymous crash logs and diagnostic telemetry to help improve system stability.",
            ),
            ConfigOption(
                key="non_workspace_access",
                label="Non-Workspace Access",
                options=["on", "off"],
                current_index=0,
                description="Allow worker agents to access files outside the current project workspace root.",
            ),
            ConfigOption(
                key="notifications",
                label="Notifications",
                options=["off", "on"],
                current_index=0,
                description="Show visual banner popups for inter-agent directives and status changes.",
            ),
            ConfigOption(
                key="queued_messages",
                label="Queued Messages",
                options=["Queue", "Discard", "Interrupt"],
                current_index=0,
                description="How to handle incoming directives while a worker process is busy executing.",
            ),
            ConfigOption(
                key="rendering_mode",
                label="Rendering Mode",
                options=["native terminal (inline)", "alternate screen"],
                current_index=0,
                description="Virtual screen rendering technique used by the pseudoterminal multiplexer.",
            ),
            ConfigOption(
                key="sandbox_mode",
                label="Sandbox Mode",
                options=["off", "on"],
                current_index=0,
                description="Run agent processes inside a sandbox with terminal and filesystem restrictions enabled.",
            ),
            ConfigOption(
                key="show_active_tasks",
                label="Show Active Tasks",
                options=["on", "off"],
                current_index=0,
                description="Display running background agent tasks and tool calls in the telemetry bars.",
            ),
            ConfigOption(
                key="show_feedback_survey",
                label="Show Feedback Survey",
                options=["on", "off"],
                current_index=0,
                description="Periodically prompt for feedback upon completing major session goals.",
            ),
            ConfigOption(
                key="show_tips",
                label="Show Tips",
                options=["on", "off"],
                current_index=0,
                description="Display contextual keyboard shortcut tips in the bottom status bar.",
            ),
            ConfigOption(
                key="tool_permission",
                label="Tool Permission",
                options=["always-proceed", "prompt", "strict"],
                current_index=0,
                description="'always-proceed': auto-approve safe tool calls. 'prompt': ask before running. 'strict': sandbox.",
            ),
            ConfigOption(
                key="use_ai_credits",
                label="Use AI Credits",
                options=["off", "on"],
                current_index=0,
                description="Enable cloud AI compute credits for advanced deep-thinking reasoning models.",
            ),
            ConfigOption(
                key="verbosity",
                label="Verbosity",
                options=["medium", "low", "high", "debug"],
                current_index=0,
                description="Logging verbosity level for terminal manager, MCP bridge, and agent orchestration.",
            ),
            # Worker Agent Specific Configurations
            ConfigOption(
                key="target_worker",
                label="Target Worker Tab",
                options=tab_options,
                current_index=target_tab_idx,
                description="Active worker agent tab being inspected, configured, or restarted.",
                is_worker_specific=True,
            ),
            ConfigOption(
                key="system_agent",
                label="System Agent / Profile",
                options=agent_names,
                current_index=0,
                description="Target discovered system CLI agent profile and dedicated token slot identifier (--agent).",
                is_worker_specific=True,
            ),
            ConfigOption(
                key="model_selection",
                label="Model Selection",
                options=[
                    "gemini-3.8-flash-high",
                    "gemini-3.8-flash-medium",
                    "gemini-3.8-flash-low",
                    "claude-sonnet-4-6",
                    "claude-opus-4-6-thinking",
                    "gpt-oss-120b-medium",
                ],
                current_index=0,
                description="Underlying foundation model powering the agent CLI session.",
                is_worker_specific=True,
            ),
            ConfigOption(
                key="reasoning_effort",
                label="Reasoning Effort",
                options=["high", "medium", "low", "xhigh", "max"],
                current_index=0,
                description="Reasoning token budget and thinking depth allocated for multi-step orchestration.",
                is_worker_specific=True,
            ),
            ConfigOption(
                key="extra_flags",
                label="Extra CLI Flags",
                options=[
                    "--dangerously-skip-permissions",
                    "--dangerously-skip-permissions --sandbox",
                    "--sandbox",
                    "none",
                ],
                current_index=0,
                description="Additional command-line startup arguments passed directly to the agy process.",
                is_worker_specific=True,
            ),
            ConfigOption(
                key="open_directive",
                label="Directives File",
                options=["[Open in System Editor (o)]"],
                current_index=0,
                description=f"Directives file: {resolve_directive_path(self._resolve_selected_worker_id())}. Press Enter or 'o' to open in default system editor.",
                is_worker_specific=True,
            ),
            ConfigOption(
                key="behavioral_directive",
                label="Role & Behavioral Directive Prompt",
                options=["[Edit In-App (e)]", "Autonomous Worker", "Architect Planner", "Code Reviewer"],
                current_index=0,
                description="Persisted in ~/.mind/directives/. Press 'e' or Enter to inspect and edit full markdown rules in-app.",
                is_worker_specific=True,
            ),
        ]

        # Apply worker defaults to options
        for opt in self.options:
            if opt.key == "agent_mode" and cur_mode:
                opt.set_value(cur_mode)
            elif opt.key == "model_selection" and cur_model:
                opt.set_value(cur_model)
            elif opt.key == "reasoning_effort" and cur_effort:
                opt.set_value(cur_effort)
            elif opt.key == "system_agent" and cur_agent:
                opt.set_value(cur_agent)
            elif opt.key == "extra_flags" and cur_flags:
                opt.set_value(cur_flags)

    def compose(self) -> ComposeResult:
        with Vertical(id="agent-config-dialog"):
            # 1. Search Bar
            with Horizontal(id="config-search-box"):
                yield Static("Search: ", id="config-search-prompt")
                yield Input(
                    placeholder="",
                    id="config-search-input",
                )

            # 2. Main Two-Column Interactive Settings List
            self.settings_list = ConfigSettingsListWidget(
                entries=self.options,
                on_change=self._on_option_changed,
                on_selection_change=self._on_selection_changed,
                id="config-settings-view",
            )
            yield self.settings_list

            # 3. Dynamic Description Footer
            initial_entry = self.settings_list.get_active_entry()
            desc = initial_entry.description if initial_entry else ""
            yield Static(desc, id="config-description-view")

            # 4. Action Hints Bar
            yield Static(
                "[bold #7aa2f7]↑↓/jk[/] Navigate  [bold #7aa2f7]←→/Space/Enter[/] Change  [bold #7aa2f7]o[/] Open Directive  [bold #7aa2f7]e[/] Edit In-App  [bold #e0af68]Ctrl+R[/] Restart  [bold #bb9af7]Esc[/] Close",
                id="config-footer-hints",
            )

    def on_mount(self) -> None:
        """Focus the settings list by default for immediate keyboard interaction."""
        self.set_timer(0.05, self._focus_list)

    def _focus_list(self) -> None:
        try:
            self.settings_list.focus()
            self._update_description()
        except Exception:
            pass

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter settings list live as user types into search input."""
        if event.input.id == "config-search-input":
            self.settings_list.set_search_query(event.value)
            self._update_description()

    def on_key(self, event: events.Key) -> None:
        """Global key interceptor for dialog navigation and shortcuts."""
        # If user presses Down, Enter, or Tab while in search input, shift focus to settings list
        if self.focused and getattr(self.focused, "id", "") == "config-search-input":
            if event.key in ("down", "enter", "tab"):
                self.settings_list.focus()
                event.stop()
                event.prevent_default()
                return
            elif event.key == "escape":
                inp = self.query_one("#config-search-input", Input)
                if inp.value:
                    inp.value = ""
                    self.settings_list.set_search_query("")
                    event.stop()
                    event.prevent_default()
                    return
                else:
                    self.action_save_and_close()
                    event.stop()
                    event.prevent_default()
                    return

        # 'q' in list exits dialog
        if event.key == "q" and self.focused == self.settings_list:
            self.action_save_and_close()
            event.stop()
            event.prevent_default()
            return

        if event.key in ("o", "ctrl+o"):
            self.action_open_directive_file()
            event.stop()
            event.prevent_default()
            return

        if event.key == "e" and self.focused == self.settings_list:
            self.action_edit_directive_inline()
            event.stop()
            event.prevent_default()
            return

    def _on_selection_changed(self, entry: ConfigOption | None) -> None:
        """Update description bar when active setting changes."""
        self._update_description()

    def _on_option_changed(self, entry: ConfigOption) -> None:
        """Handle option value changes dynamically."""
        self._update_description()

        if entry.key == "open_directive":
            self.action_open_directive_file()
            return

        if entry.key == "behavioral_directive":
            self.action_edit_directive_inline()
            return

        # If Target Worker Tab was changed, synchronize agent-specific values
        if entry.key == "target_worker":
            selected_worker_id = self._resolve_selected_worker_id()
            worker = self._terminal_manager.get_worker(selected_worker_id)
            if worker:
                for opt in self.options:
                    if opt.key == "agent_mode" and worker.cli_mode:
                        opt.set_value(worker.cli_mode)
                    elif opt.key == "model_selection" and worker.model:
                        opt.set_value(worker.model)
                    elif opt.key == "reasoning_effort" and worker.reasoning_effort:
                        opt.set_value(worker.reasoning_effort)
                    elif opt.key == "system_agent" and worker.assigned_agent:
                        opt.set_value(worker.assigned_agent)
                    elif opt.key == "extra_flags" and worker.extra_flags:
                        opt.set_value(worker.extra_flags)
                    elif opt.key == "open_directive":
                        opt.description = f"Directives file: {resolve_directive_path(selected_worker_id)}. Press Enter or 'o' to open in editor."
                self.settings_list.refresh()

    def _resolve_directive_target(self) -> str:
        """Resolve the target agent slot / identifier for directive persistence."""
        selected_id = self._resolve_selected_worker_id()
        worker = self._terminal_manager.get_worker(selected_id)
        if worker and worker.assigned_agent:
            return worker.assigned_agent
        for opt in self.options:
            if opt.key == "system_agent" and opt.value:
                return opt.value
        return selected_id

    def action_open_directive_file(self) -> None:
        """Open the active worker agent's directive Markdown file in the system default editor."""
        target_id = self._resolve_directive_target()
        path = open_directive_in_editor(target_id)
        try:
            if hasattr(self, "app") and hasattr(self.app, "notify"):
                self.app.notify(f"📄 Directives File: {path}", title="Directives Open", severity="information", timeout=3.0)
        except Exception:
            pass

    def action_edit_directive_inline(self) -> None:
        """Open the in-app directive editor modal for the currently selected worker."""
        target_id = self._resolve_directive_target()
        current_content = load_directive(target_id)
        try:
            self.app.push_screen(
                DirectiveEditorModal(
                    target=target_id,
                    current_content=current_content,
                ),
                callback=self._on_directive_edited,
            )
        except Exception:
            pass

    def _on_directive_edited(self, new_text: str | None) -> None:
        """Callback when directive is saved from DirectiveEditorModal."""
        if new_text is not None:
            worker_id = self._resolve_selected_worker_id()
            directive_target = self._resolve_directive_target()
            save_directive(directive_target, new_text)
            worker = self._terminal_manager.get_worker(worker_id)
            if worker:
                worker.instructions = new_text
                worker.profile.instructions = new_text
            try:
                if hasattr(self, "app") and hasattr(self.app, "notify"):
                    self.app.notify("✓ Directive updated & saved to disk", severity="information", timeout=2.0)
            except Exception:
                pass

    def _update_description(self) -> None:
        """Update contextual description display."""
        try:
            desc_widget = self.query_one("#config-description-view", Static)
            entry = self.settings_list.get_active_entry()
            if entry and entry.description:
                desc_widget.update(Text.from_markup(f"[dim]{entry.description}[/]"))
            else:
                desc_widget.update("")
        except Exception:
            pass

    def _resolve_selected_worker_id(self) -> str:
        """Determine target worker id from selected Target Worker Tab option."""
        for opt in self.options:
            if opt.key == "target_worker":
                val = opt.value
                if "coordinator" in val.lower():
                    return "coordinator"
                m = re.search(r"tab\s*(\d+)", val, re.IGNORECASE)
                if m:
                    return m.group(1)
        return self._default_target or "1"

    def _gather_config_dict(self) -> dict[str, Any]:
        """Collect current values into configuration dictionary."""
        config_map: dict[str, str] = {opt.key: opt.value for opt in self.options}

        extra_flags = config_map.get("extra_flags", "")
        if extra_flags == "none":
            extra_flags = ""

        cli_mode = config_map.get("agent_mode", "auto")
        if cli_mode == "default":
            cli_mode = "auto"

        assigned_agent = config_map.get("system_agent", "")
        name = assigned_agent or f"Worker-{self._resolve_selected_worker_id()}"

        return {
            "name": name,
            "cli_mode": cli_mode,
            "model": config_map.get("model_selection", "gemini-3.8-flash-high"),
            "reasoning_effort": config_map.get("reasoning_effort", "high"),
            "extra_flags": extra_flags,
            "assigned_agent": assigned_agent,
            "instructions": "",
            # Global settings
            "animation_speed": config_map.get("animation_speed", "fast"),
            "copy_on_select": config_map.get("copy_on_select", "on") == "on",
            "editor_mode": config_map.get("editor_mode", "vim"),
            "color_scheme": config_map.get("color_scheme", "colorblind-friendly dark"),
        }

    def action_save_and_close(self) -> None:
        """Save configuration without restarting worker process and dismiss modal."""
        target_id = self._resolve_selected_worker_id()
        new_config = self._gather_config_dict()

        # Update worker in TerminalManager
        worker = self._terminal_manager.get_worker(target_id)
        if worker:
            worker.cli_mode = new_config["cli_mode"]
            worker.model = new_config["model"]
            worker.reasoning_effort = new_config["reasoning_effort"]
            worker.extra_flags = new_config["extra_flags"]
            worker.profile.cli_mode = new_config["cli_mode"]
            worker.profile.model = new_config["model"]
            worker.profile.reasoning_effort = new_config["reasoning_effort"]
            worker.profile.extra_flags = new_config["extra_flags"]

        if self._on_save_callback:
            try:
                self._on_save_callback(target_id, new_config, False)
            except Exception:
                pass

        self.dismiss(None)

    def action_save_and_restart(self) -> None:
        """Save configuration, restart child worker process in PTY, and dismiss modal."""
        target_id = self._resolve_selected_worker_id()
        new_config = self._gather_config_dict()

        # Respawn worker through TerminalManager
        try:
            self._terminal_manager.restart_worker(target_id, new_config)
            try:
                if hasattr(self, "app") and hasattr(self.app, "notify"):
                    self.app.notify(f"⚡ Config applied & Worker {target_id} restarted", severity="information", timeout=2.0)
            except Exception:
                pass
        except Exception as e:
            try:
                if hasattr(self, "app") and hasattr(self.app, "notify"):
                    self.app.notify(f"Restart error: {e}", severity="error", timeout=3.0)
            except Exception:
                pass

        if self._on_save_callback:
            try:
                self._on_save_callback(target_id, new_config, True)
            except Exception:
                pass

        self.dismiss(None)
