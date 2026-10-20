"""Directives and System Prompts Management for mind Agents.

Externalizes agent behavioral rules, principles, and system prompts to editable
Markdown files on disk:
- Coordinator directive: `~/.mind/directives/coordinator.md`
- Sub-agent worker directives: `~/.mind/directives/workers/<agent_slot>.md` (e.g. agy1.md, agy2.md)

Provides utilities for reading, persisting, and opening directive files in the
system default editor or TUI.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import subprocess
import sys

logger = logging.getLogger("mind.directives")

DEFAULT_COORDINATOR_DIRECTIVE = """# Primary Coordinator Directive
You are the Primary Coordinator for the `mind` multi-agent terminal multiplexer.

## Role & Responsibilities:
- Stand by in an idle state for explicit user instructions.
- Never run unsolicited scans or auto-prompts without user request.
- When given a task by the user, decompose the objective into modular sub-tasks.
- Actively delegate tasks to the worker agents in the right pane using mind-bridge MCP tools:
  * `list_workers()`: Check available worker slots and active states.
  * `send_terminal_input(worker_id, text)`: Dispatch commands or prompts to worker terminals.
  * `get_terminal_screen(worker_id)`: Inspect worker outputs and verify results.
  * `interrupt_and_inject(worker_id, message)`: Redirect workers if an issue occurs.
- Monitor worker completion alerts and report concise summaries back to the user.
"""

DEFAULT_WORKER_DIRECTIVE_TEMPLATE = """# Worker Agent Directive ({slot})
You are an autonomous worker agent operating in slot `{slot}`.

## Principles:
1. Maintain an idle standby state until a task is assigned by the user or coordinator.
2. Execute terminal commands accurately with clean, deterministic edits.
3. Keep code modular, adhere to existing directory architectures, and update documentation.
4. When execution finishes, return cleanly to the terminal prompt so completion can be detected.
5. Report any blockers or errors immediately.
"""


def get_directives_dir() -> Path:
    """Return the base directory for mind directives (~/.mind/directives)."""
    base = Path.home() / ".mind" / "directives"
    base.mkdir(parents=True, exist_ok=True)
    (base / "workers").mkdir(parents=True, exist_ok=True)
    return base


def get_coordinator_directive_path() -> Path:
    """Return absolute path to the coordinator directive markdown file."""
    return get_directives_dir() / "coordinator.md"


def get_worker_directive_path(agent_slot: str) -> Path:
    """Return absolute path to a worker agent's directive markdown file."""
    slot = agent_slot.strip().lower()
    if not slot.endswith(".md"):
        filename = f"{slot}.md"
    else:
        filename = slot
    return get_directives_dir() / "workers" / filename


def resolve_directive_path(target: str) -> Path:
    """Resolve target name ('coordinator', 'primary', 'agy1', '1', etc.) to a file path."""
    t = str(target).strip().lower()
    if t in ("coordinator", "primary", "0"):
        return get_coordinator_directive_path()
    if not t.startswith("agy") and t.isdigit():
        t = f"agy{t}"
    return get_worker_directive_path(t)


def ensure_default_directives() -> None:
    """Ensure standard coordinator and worker directive files exist on disk."""
    coord_path = get_coordinator_directive_path()
    if not coord_path.exists():
        try:
            coord_path.write_text(DEFAULT_COORDINATOR_DIRECTIVE, encoding="utf-8")
            logger.info("Initialized default coordinator directive at %s", coord_path)
        except Exception as e:
            logger.warning("Could not write default coordinator directive: %s", e)

    for slot_num in range(1, 6):
        worker_slot = f"agy{slot_num}"
        w_path = get_worker_directive_path(worker_slot)
        if not w_path.exists():
            try:
                content = DEFAULT_WORKER_DIRECTIVE_TEMPLATE.format(slot=worker_slot)
                w_path.write_text(content, encoding="utf-8")
                logger.info("Initialized default worker directive at %s", w_path)
            except Exception as e:
                logger.warning("Could not write worker directive for %s: %s", worker_slot, e)


def load_directive(target: str) -> str:
    """Read directive text from disk, initializing with default guidelines if absent."""
    ensure_default_directives()
    path = resolve_directive_path(target)
    if path.exists():
        try:
            return path.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception as e:
            logger.error("Failed to read directive file at %s: %s", path, e)

    # Fallback to in-memory template
    t = str(target).strip().lower()
    if t in ("coordinator", "primary", "0"):
        return DEFAULT_COORDINATOR_DIRECTIVE.strip()
    slot = f"agy{t}" if t.isdigit() else t
    return DEFAULT_WORKER_DIRECTIVE_TEMPLATE.format(slot=slot).strip()


def save_directive(target: str, content: str) -> Path:
    """Save updated directive content to its persistent Markdown file."""
    path = resolve_directive_path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    logger.info("Saved persistent directive to %s", path)
    return path


def open_directive_in_editor(target: str) -> Path:
    """Open the directive file in the system default text editor or viewer."""
    ensure_default_directives()
    path = resolve_directive_path(target)

    if sys.platform == "win32":
        try:
            os.startfile(str(path))
            return path
        except Exception:
            pass

    # Fallback to environment editor or notepad
    editor = os.environ.get("EDITOR") or ("notepad.exe" if sys.platform == "win32" else "nano")
    try:
        subprocess.Popen([editor, str(path)])
    except Exception as e:
        logger.warning("Could not open editor for %s: %s", path, e)
    return path
