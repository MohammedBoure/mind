"""Agent Assignment & Task Dispatcher Modal.

Allows selecting an agent (Primary or Worker 1..N), defining its role and assigned
task prompt, and dispatching the prompt directly into its running agy.exe instance.
"""

from __future__ import annotations

import sys
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from mind.core.terminal_manager import TerminalManager


_ROLE_OPTIONS = [
    ("Worker (Autonomous Execution)", "worker"),
    ("Code Reviewer (Quality & Verification)", "code-reviewer"),
    ("Test Engineer (Pytest & Edge Cases)", "tester"),
    ("Researcher (Documentation & Design)", "researcher"),
    ("Primary Coordinator (High-Level)", "coordinator"),
]

_DISPATCH_MODES = [
    ("⚡ Interrupt & Inject (SIGINT + Prompt)", "interrupt"),
    ("⌨ Direct Stdin Stream (Type + Enter)", "direct"),
]


class DirectiveModal(ModalScreen[None]):
    """Modal overlay allowing agent assignment and direct task dispatch."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, default_target: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._default_target = default_target
        self._terminal_manager = TerminalManager.get_instance()

    def compose(self) -> ComposeResult:
        workers = self._terminal_manager.list_workers()
        target_options: list[tuple[str, str]] = []
        has_primary = False
        for w in workers:
            if w.role == "coordinator" or str(w.worker_id) in ("coordinator", "primary"):
                target_options.insert(0, (f"🧠 Primary Coordinator (PID: {w.pid or '-'})", str(w.worker_id)))
                has_primary = True
            else:
                target_options.append((f"⚡ {w.name} (PID: {w.pid or '-'})", str(w.worker_id)))
        if not has_primary:
            target_options.insert(0, ("🧠 Primary Agent (Coordinator)", "primary"))
        if len(target_options) == 1:
            target_options.append(("⚡ Worker-1 (Default)", "1"))
            target_options.append(("⚡ Worker-2 (Default)", "2"))

        default_val = self._default_target or (target_options[1][1] if len(target_options) > 1 else "primary")

        with Vertical(id="directive-modal-dialog"):
            yield Static("⚡ [bold #e0af68]Agent Assignment & Task Dispatcher[/]", id="directive-title")
            yield Static(
                "[dim]Assign role, specify task prompt, and dispatch directly to running agy instance.[/]",
                id="directive-subtitle",
            )

            with Vertical(classes="modal-field"):
                yield Label("Target Agent:", classes="modal-label")
                yield Select(
                    options=target_options,
                    value=default_val,
                    id="target-agent-select",
                    allow_blank=False,
                )

            with Vertical(classes="modal-field"):
                yield Label("Agent Role Assignment:", classes="modal-label")
                yield Select(
                    options=_ROLE_OPTIONS,
                    value="worker",
                    id="role-select",
                    allow_blank=False,
                )

            with Vertical(classes="modal-field"):
                yield Label("Assigned Task / Directive Prompt:", classes="modal-label")
                yield Input(
                    placeholder="e.g. Inspect codebase, verify test coverage, and fix bugs",
                    id="task-prompt-input",
                )

            with Vertical(classes="modal-field"):
                yield Label("Execution Dispatch Mode:", classes="modal-label")
                yield Select(
                    options=_DISPATCH_MODES,
                    value="interrupt",
                    id="dispatch-mode-select",
                    allow_blank=False,
                )

            with Horizontal(id="directive-buttons"):
                yield Button("⚡ Dispatch Task", variant="warning", id="btn-inject-submit")
                yield Button("Cancel", variant="default", id="btn-inject-cancel")

    def on_mount(self) -> None:
        """Focus task prompt input by default."""
        self.query_one("#task-prompt-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-inject-submit":
            self._submit_dispatch()
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit_dispatch()

    def _submit_dispatch(self) -> None:
        target_select = self.query_one("#target-agent-select", Select)
        role_select = self.query_one("#role-select", Select)
        prompt_input = self.query_one("#task-prompt-input", Input)
        dispatch_select = self.query_one("#dispatch-mode-select", Select)

        target_id = str(target_select.value) if target_select.value else "1"
        role_val = str(role_select.value) if role_select.value else "worker"
        prompt_text = prompt_input.value.strip()
        dispatch_mode = str(dispatch_select.value) if dispatch_select.value else "interrupt"

        if not prompt_text:
            prompt_input.focus()
            self._safe_notify("Please enter a task prompt or directive.", severity="error")
            return

        if target_id in ("primary", "coordinator"):
            coord = self._terminal_manager.get_worker("coordinator") or self._terminal_manager.get_worker("primary")
            if coord and coord.is_alive:
                coord.task = prompt_text
                coord.role = role_val
                coord.profile.role = role_val
                if dispatch_mode == "interrupt":
                    coord.interrupt_and_inject(
                        sender_id="User / Mind UI",
                        message=prompt_text,
                        priority="high",
                    )
                else:
                    newline = "\r\n" if sys.platform == "win32" else "\n"
                    coord.write(prompt_text + newline)
                self._safe_notify("✓ Directive dispatched to Primary Coordinator!", severity="warning")
            else:
                self._safe_notify(f"✓ Task assigned to Primary Agent ({role_val}): '{prompt_text}'", severity="information")
            self.dismiss(None)
            return

        # Lookup worker in terminal manager
        worker = self._terminal_manager.get_worker(target_id)
        if not worker:
            self._safe_notify(f"Worker '{target_id}' not found.", severity="error")
            self.dismiss(None)
            return

        # Update worker profile & task assignment
        worker.task = prompt_text
        worker.role = role_val
        worker.profile.role = role_val

        # Dispatch prompt to the live agy.exe process
        if dispatch_mode == "interrupt":
            worker.interrupt_and_inject(
                sender_id="Primary Coordinator",
                message=prompt_text,
                priority="high",
            )
        else:
            newline = "\r\n" if sys.platform == "win32" else "\n"
            worker.write(prompt_text + newline)

        self._safe_notify(f"✓ Task dispatched to {worker.name} ({role_val})!", severity="warning")
        self.dismiss(None)

    def _safe_notify(self, message: str, severity: str = "information") -> None:
        try:
            self.notify(message, severity=severity)
        except Exception:
            pass

    def action_cancel(self) -> None:
        self.dismiss(None)
