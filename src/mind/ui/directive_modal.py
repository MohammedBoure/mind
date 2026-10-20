"""Directive Injection Modal dialog for sending prioritized directives to workers via MCP."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from mind.core.terminal_manager import TerminalManager


_PRIORITY_OPTIONS = [
    ("Critical (Red Alert)", "critical"),
    ("High (Default)", "high"),
    ("Normal (Informational)", "normal"),
    ("Low (Background)", "low"),
]


class DirectiveModal(ModalScreen[None]):
    """Modal overlay allowing the user to inject directives into any worker."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, default_target: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._default_target = default_target
        self._terminal_manager = TerminalManager.get_instance()

    def compose(self) -> ComposeResult:
        workers = self._terminal_manager.list_workers()
        target_options = [(f"{w.name} (PID: {w.pid or '-'})", w.worker_id) for w in workers]
        if not target_options:
            target_options = [("Worker-1", "worker-1"), ("Worker-2", "worker-2")]

        default_val = self._default_target or (target_options[0][1] if target_options else "worker-1")

        with Vertical(id="directive-modal-dialog"):
            yield Static("⚡  [bold #e0af68]Inject Inter-Agent Directive[/]", id="directive-title")
            yield Static(
                "[dim]Sends SIGINT to halt ongoing execution, waits for prompt to settle, and injects directive.[/]",
                id="directive-subtitle",
            )

            with Vertical(classes="modal-field"):
                yield Label("Target Worker Agent:", classes="modal-label")
                yield Select(
                    options=target_options,
                    value=default_val,
                    id="target-worker-select",
                    allow_blank=False,
                )

            with Vertical(classes="modal-field"):
                yield Label("Sender Profile / Identifier:", classes="modal-label")
                yield Input(
                    value="primary-coordinator",
                    placeholder="e.g. primary-coordinator, supervisor",
                    id="sender-input",
                )

            with Vertical(classes="modal-field"):
                yield Label("Priority Level:", classes="modal-label")
                yield Select(
                    options=_PRIORITY_OPTIONS,
                    value="high",
                    id="priority-select",
                    allow_blank=False,
                )

            with Vertical(classes="modal-field"):
                yield Label("Directive Message / Instructions:", classes="modal-label")
                yield Input(
                    placeholder="e.g. Stop current build. Verify module imports first.",
                    id="message-input",
                )

            with Horizontal(id="directive-buttons"):
                yield Button("⚡ Inject Directive", variant="warning", id="btn-inject-submit")
                yield Button("Cancel", variant="default", id="btn-inject-cancel")

    def on_mount(self) -> None:
        """Focus message input by default."""
        self.query_one("#message-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-inject-submit":
            self._submit_injection()
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit_injection()

    def _submit_injection(self) -> None:
        target_select = self.query_one("#target-worker-select", Select)
        sender_input = self.query_one("#sender-input", Input)
        prio_select = self.query_one("#priority-select", Select)
        msg_input = self.query_one("#message-input", Input)

        target_id = str(target_select.value) if target_select.value else "worker-1"
        sender_id = sender_input.value.strip() or "primary-coordinator"
        priority = str(prio_select.value) if prio_select.value else "high"
        message = msg_input.value.strip()

        if not message:
            msg_input.focus()
            self.notify("Please enter a directive message.", severity="error")
            return

        worker = self._terminal_manager.get_worker(target_id)
        if not worker:
            self.notify(f"Worker '{target_id}' not found.", severity="error")
            self.dismiss(None)
            return

        # Perform injection via terminal manager
        result = worker.interrupt_and_inject(
            sender_id=sender_id,
            message=message,
            priority=priority,
        )
        self.notify(f"✓ Directive injected into {worker.name}!", severity="warning")
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)
