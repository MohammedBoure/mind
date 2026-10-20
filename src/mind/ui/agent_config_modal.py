"""Interactive in-app Agent Configuration Modal.

Allows inspecting, configuring, and tuning CLI flags, models, reasoning effort,
and directives for individual worker agents directly from the TUI without editing files.
"""

from __future__ import annotations

from typing import Any, Callable
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static, TextArea

from mind.core.terminal_manager import TerminalManager


class DirectiveTextArea(TextArea):
    """Multi-line text area supporting smooth Tab / Shift+Tab keyboard focus traversal."""

    def on_key(self, event: events.Key) -> None:
        if event.key == "tab":
            self.screen.focus_next()
            event.stop()
            event.prevent_default()
        elif event.key == "shift+tab":
            self.screen.focus_previous()
            event.stop()
            event.prevent_default()


_CLI_MODES = [
    ("Auto (Autonomous Execution)", "auto"),
    ("Accept Edits (Auto-Apply Tool Edits)", "accept-edits"),
    ("Plan (Read-only Analysis & Planning)", "plan"),
]

_MODEL_PRESETS = [
    ("Gemini 3.8 Flash High (Default)", "gemini-3.8-flash-high"),
    ("Gemini 3.8 Flash Medium", "gemini-3.8-flash-medium"),
    ("Gemini 3.8 Flash Low", "gemini-3.8-flash-low"),
    ("Claude Sonnet 4.6 (Thinking)", "claude-sonnet-4-6"),
    ("Claude Opus 4.6 (Thinking)", "claude-opus-4-6-thinking"),
    ("GPT-OSS 120B Medium", "gpt-oss-120b-medium"),
    ("Custom Model Name...", "custom"),
]

_EFFORT_OPTIONS = [
    ("Low", "low"),
    ("Medium", "medium"),
    ("High (Default)", "high"),
    ("Extra High (xhigh)", "xhigh"),
    ("Max", "max"),
]


class AgentConfigModal(ModalScreen[None]):
    """Modal overlay for inspecting and tuning worker agent CLI arguments and profiles."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
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

    def compose(self) -> ComposeResult:
        workers = self._terminal_manager.list_workers()
        target_options: list[tuple[str, str]] = []
        for w in workers:
            alias_display = w.name if w.name and w.name != f"Worker-{w.worker_id}" else f"agy{w.worker_id}"
            target_options.append((f"⚡ Worker-{w.worker_id} ({alias_display})", str(w.worker_id)))

        if not target_options:
            target_options = [
                ("⚡ Worker-1 (agy1)", "1"),
                ("⚡ Worker-2 (agy2)", "2"),
            ]

        default_val = self._default_target or target_options[0][1]
        # Ensure default_val exists in target_options
        valid_keys = {val for _, val in target_options}
        if default_val not in valid_keys:
            default_val = target_options[0][1]

        with Vertical(id="agent-config-dialog"):
            yield Static("⚙ [bold #bb9af7]Agent Configuration & CLI Tuning[/]", id="config-title")
            yield Static(
                "[dim]Tune CLI flags, model, reasoning effort, and directives per worker agent.[/]",
                id="config-subtitle",
            )

            with VerticalScroll(id="config-scroll-body"):
                # 1. Target Worker
                with Vertical(classes="modal-field"):
                    yield Label("Target Worker Agent:", classes="modal-label")
                    yield Select(
                        options=target_options,
                        value=default_val,
                        id="target-worker-select",
                        allow_blank=False,
                    )

                # 2. Agent Name / Alias
                with Vertical(classes="modal-field"):
                    yield Label("Agent Alias / Name:", classes="modal-label")
                    yield Input(
                        placeholder="e.g. agy 1 or Worker-1",
                        id="worker-alias-input",
                    )

                # 3. Execution Mode
                with Vertical(classes="modal-field"):
                    yield Label("Agent Execution Mode (--mode):", classes="modal-label")
                    yield Select(
                        options=_CLI_MODES,
                        value="auto",
                        id="cli-mode-select",
                        allow_blank=False,
                    )

                # 4. Model Preset & Custom Model Name
                with Vertical(classes="modal-field"):
                    yield Label("Model Selection (--model):", classes="modal-label")
                    yield Select(
                        options=_MODEL_PRESETS,
                        value="gemini-3.8-flash-high",
                        id="model-preset-select",
                        allow_blank=False,
                    )
                    yield Input(
                        placeholder="Model name identifier (e.g. gemini-3.8-flash-high)",
                        id="model-name-input",
                    )

                # 5. Reasoning Effort
                with Vertical(classes="modal-field"):
                    yield Label("Reasoning Effort (--effort):", classes="modal-label")
                    yield Select(
                        options=_EFFORT_OPTIONS,
                        value="high",
                        id="reasoning-effort-select",
                        allow_blank=False,
                    )

                # 6. Extra Flags
                with Vertical(classes="modal-field"):
                    yield Label("Extra CLI Flags (e.g. --dangerously-skip-permissions --sandbox):", classes="modal-label")
                    yield Input(
                        placeholder="--dangerously-skip-permissions --sandbox",
                        id="extra-flags-input",
                    )

                # 7. Role & Behavioral Directive
                with Vertical(classes="modal-field"):
                    yield Label("Role & Behavioral Directive Prompt:", classes="modal-label")
                    yield DirectiveTextArea(
                        text="",
                        id="instructions-area",
                    )

            # Action Buttons
            with Horizontal(id="config-buttons"):
                yield Button("⚡ Save & Restart Worker", variant="warning", id="btn-save-restart")
                yield Button("💾 Save without Restart", variant="primary", id="btn-save-only")
                yield Button("Cancel", variant="default", id="btn-config-cancel")

    def on_mount(self) -> None:
        """Populate initial fields with the active worker's existing configuration."""
        target_select = self.query_one("#target-worker-select", Select)
        initial_id = str(target_select.value) if target_select.value else (self._default_target or "1")
        self._load_worker_data(initial_id)
        self.query_one("#worker-alias-input", Input).focus()

    def on_select_changed(self, event: Select.Changed) -> None:
        """Dynamically load worker configuration when target selector changes, or sync model input."""
        if event.select.id == "target-worker-select":
            if event.value is not None:
                self._load_worker_data(str(event.value))
        elif event.select.id == "model-preset-select":
            if event.value and event.value != "custom":
                try:
                    self.query_one("#model-name-input", Input).value = str(event.value)
                except Exception:
                    pass

    def _load_worker_data(self, worker_id: str) -> None:
        """Populate form fields with current values from the worker session."""
        worker = self._terminal_manager.get_worker(worker_id)
        if not worker:
            return

        try:
            alias_input = self.query_one("#worker-alias-input", Input)
            alias_input.value = worker.name

            mode_select = self.query_one("#cli-mode-select", Select)
            if worker.cli_mode in ("auto", "accept-edits", "plan"):
                mode_select.value = worker.cli_mode
            else:
                mode_select.value = "auto"

            model_input = self.query_one("#model-name-input", Input)
            current_model = worker.model or "gemini-3.8-flash-high"
            model_input.value = current_model

            preset_select = self.query_one("#model-preset-select", Select)
            preset_values = {val for _, val in _MODEL_PRESETS}
            if current_model in preset_values and current_model != "custom":
                preset_select.value = current_model
            else:
                preset_select.value = "custom"

            effort_select = self.query_one("#reasoning-effort-select", Select)
            if worker.reasoning_effort in ("low", "medium", "high", "xhigh", "max"):
                effort_select.value = worker.reasoning_effort
            else:
                effort_select.value = "high"

            flags_input = self.query_one("#extra-flags-input", Input)
            flags_input.value = worker.extra_flags or ""

            inst_area = self.query_one("#instructions-area", DirectiveTextArea)
            inst_area.load_text(worker.instructions or worker.profile.instructions or "")
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button actions."""
        if event.button.id == "btn-save-restart":
            self._save_configuration(restart=True)
        elif event.button.id == "btn-save-only":
            self._save_configuration(restart=False)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        """Close modal on escape."""
        self.dismiss(None)

    def _save_configuration(self, restart: bool) -> None:
        """Persist configuration updates to worker session and optionally restart PTY process."""
        target_select = self.query_one("#target-worker-select", Select)
        alias_input = self.query_one("#worker-alias-input", Input)
        mode_select = self.query_one("#cli-mode-select", Select)
        model_input = self.query_one("#model-name-input", Input)
        effort_select = self.query_one("#reasoning-effort-select", Select)
        flags_input = self.query_one("#extra-flags-input", Input)
        inst_area = self.query_one("#instructions-area", DirectiveTextArea)

        target_id = str(target_select.value) if target_select.value else "1"
        alias = alias_input.value.strip()
        cli_mode = str(mode_select.value) if mode_select.value else "auto"
        model = model_input.value.strip() or "gemini-3.8-flash-high"
        effort = str(effort_select.value) if effort_select.value else "high"
        extra_flags = flags_input.value.strip()
        instructions = inst_area.text.strip()

        new_config = {
            "name": alias,
            "cli_mode": cli_mode,
            "model": model,
            "reasoning_effort": effort,
            "extra_flags": extra_flags,
            "instructions": instructions,
        }

        worker = self._terminal_manager.get_worker(target_id)
        if not worker:
            self._safe_notify(f"Worker '{target_id}' not found.", severity="error")
            self.dismiss(None)
            return

        if restart:
            self._terminal_manager.restart_worker(target_id, new_config=new_config)
            self._safe_notify(f"⚡ Worker '{alias or target_id}' restarted with updated CLI flags!", severity="warning")
        else:
            if alias:
                worker.name = alias
            worker.cli_mode = cli_mode
            worker.model = model
            worker.reasoning_effort = effort
            worker.extra_flags = extra_flags
            worker.instructions = instructions
            worker.profile.cli_mode = cli_mode
            worker.profile.model = model
            worker.profile.reasoning_effort = effort
            worker.profile.extra_flags = extra_flags
            worker.profile.instructions = instructions
            self._safe_notify(f"✓ Configuration saved for Worker '{alias or target_id}' (no restart).", severity="information")

        if self._on_save_callback:
            try:
                self._on_save_callback(target_id, new_config, restart)
            except Exception:
                pass

        self.dismiss(None)

    def _safe_notify(self, message: str, severity: str = "information") -> None:
        """Safely trigger application toast notification."""
        try:
            if hasattr(self.app, "notify"):
                self.app.notify(message, severity=severity, timeout=3.5)
        except Exception:
            pass
