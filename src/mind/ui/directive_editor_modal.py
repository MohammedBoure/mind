"""In-app modal editor for inspecting and editing agent directive markdown directly."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static, TextArea

from mind.core.directives import (
    open_directive_in_editor,
    resolve_directive_path,
    save_directive,
)


class DirectiveEditorModal(ModalScreen[str | None]):
    """In-app modal editor for inspecting and editing agent directive markdown directly."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+s", "save_directive_content", "Save Directive"),
        ("ctrl+o", "open_in_editor", "Open in External Editor"),
    ]

    def __init__(self, target: str, current_content: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.target = target
        self.current_content = current_content
        self.file_path = resolve_directive_path(target)

    def compose(self) -> ComposeResult:
        with Vertical(id="directive-editor-dialog"):
            yield Static(
                f"📝 [bold #bb9af7]Edit Directive: {self.target}[/] [dim]({self.file_path})[/]",
                id="directive-editor-title",
            )
            self.text_area = TextArea(self.current_content, id="directive-text-area")
            yield self.text_area
            with Horizontal(id="directive-editor-buttons"):
                yield Button("💾 Save Directive (Ctrl+S)", variant="success", id="btn-save-directive")
                yield Button("📄 Open in External Editor (Ctrl+O)", variant="primary", id="btn-open-ext")
                yield Button("Cancel (Esc)", variant="default", id="btn-cancel-directive")

    def on_mount(self) -> None:
        self.set_timer(0.05, self._focus_text)

    def _focus_text(self) -> None:
        try:
            self.text_area.focus()
        except Exception:
            pass

    def action_save_directive_content(self) -> None:
        """Persist edited directive to disk and dismiss modal."""
        new_text = self.text_area.text
        save_directive(self.target, new_text)
        self.dismiss(new_text)

    def action_open_in_editor(self) -> None:
        """Open in system default external editor."""
        path = open_directive_in_editor(self.target)
        if hasattr(self.app, "notify"):
            self.app.notify(f"Opened: {path}", severity="information")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn-save-directive":
            self.action_save_directive_content()
        elif btn_id == "btn-open-ext":
            self.action_open_in_editor()
        elif btn_id == "btn-cancel-directive":
            self.action_cancel()
