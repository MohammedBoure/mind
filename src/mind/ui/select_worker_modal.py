"""Modal dialog for selecting an agys instance to assign to a worker tab."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, OptionList, Static
from textual.widgets.option_list import Option

from mind.core.agent_discovery import SlotInfo, discover_agent_slots, discover_system_agents


class SelectWorkerModal(ModalScreen[str | None]):
    """Modal dialog allowing the user to pick an agys instance as a worker."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("enter", "select_current", "Select"),
    ]

    def __init__(
        self,
        current_assigned: Sequence[str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.current_assigned = set(current_assigned or [])
        self.slots: list[SlotInfo] = []
        self.filtered_slots: list[SlotInfo] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="select-worker-dialog"):
            yield Static("  [bold #7aa2f7]Select Worker Agent Slot[/bold #7aa2f7]", id="modal-title")
            yield Static(
                "[dim]Choose an installed agys instance to assign as this worker's runtime environment[/dim]",
                classes="modal-subtitle",
            )

            with Vertical(classes="modal-field"):
                yield Input(
                    placeholder="Filter agy instances (e.g. agy11, email)...",
                    id="worker-search-input",
                )

            yield OptionList(id="worker-options-list")

            with Horizontal(id="modal-buttons"):
                yield Button("Select", variant="success", id="btn-select")
                yield Button("Cancel", variant="default", id="btn-cancel")

    def on_mount(self) -> None:
        self.load_options()
        try:
            self.query_one("#worker-options-list", OptionList).focus()
        except Exception:
            pass

    def load_options(self, query: str = "") -> None:
        try:
            self.slots = discover_agent_slots()
        except Exception:
            names = discover_system_agents()
            self.slots = [
                SlotInfo(
                    slot_id=int(n.replace("agy", "")) if n.replace("agy", "").isdigit() else 1,
                    name=n,
                    instance_dir=Path(n),
                    token_file=Path(n),
                    instance_token_file=Path(n),
                    has_token=True,
                    email=None,
                )
                for n in names
            ]

        option_list = self.query_one("#worker-options-list", OptionList)
        option_list.clear_options()

        q = query.strip().lower()
        self.filtered_slots = []
        for s in self.slots:
            if q:
                match = (q in s.name.lower()) or (s.email and q in s.email.lower())
                if not match:
                    continue
            self.filtered_slots.append(s)

        if not self.filtered_slots:
            option_list.add_option(
                Option("[dim italic]No matching agys instances found.[/dim italic]", id=None)
            )
            return

        for s in self.filtered_slots:
            is_assigned = s.name in self.current_assigned
            if is_assigned:
                status_badge = "[dim #e0af68]● In Use[/]"
            elif s.has_token:
                status_badge = "[bold #9ece6a]● Ready[/]"
            else:
                status_badge = "[dim #565f89]○ Unauthenticated[/]"

            email_str = f"[dim #7dcfff]{s.email}[/]" if s.email else "[dim #565f89](No email / local profile)[/]"
            label = (
                f"[bold #7aa2f7]{s.name:<10}[/]  "
                f"{status_badge:<18}  "
                f"{email_str}"
            )
            option_list.add_option(Option(label, id=s.name))

        if option_list.option_count > 0:
            option_list.highlighted = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "worker-search-input":
            self.load_options(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "worker-search-input":
            self.action_select_current()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is not None:
            self.dismiss(str(event.option.id))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-select":
            self.action_select_current()
        else:
            self.dismiss(None)

    def action_select_current(self) -> None:
        opt_list = self.query_one("#worker-options-list", OptionList)
        if (
            opt_list.highlighted is not None
            and 0 <= opt_list.highlighted < len(self.filtered_slots)
        ):
            chosen = self.filtered_slots[opt_list.highlighted].name
            self.dismiss(chosen)
        elif self.filtered_slots:
            self.dismiss(self.filtered_slots[0].name)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_cursor_down(self) -> None:
        opt_list = self.query_one("#worker-options-list", OptionList)
        if opt_list.highlighted is not None and opt_list.highlighted < opt_list.option_count - 1:
            opt_list.highlighted += 1

    def action_cursor_up(self) -> None:
        opt_list = self.query_one("#worker-options-list", OptionList)
        if opt_list.highlighted is not None and opt_list.highlighted > 0:
            opt_list.highlighted -= 1
