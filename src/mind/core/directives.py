"""Directives and System Prompts Management for mind Agents.

Externalizes agent behavioral rules, principles, and system prompts to editable
Markdown files on disk:
- Coordinator directive: `~/.mind/directives/coordinator.md`
- Sub-agent worker directives: `~/.mind/directives/workers/<agent_slot>.md` (e.g. agy1.md, agy2.md)

Provides utilities for:
- Reading, writing, and resolving directive files.
- Real-time automatic monitoring and instant hot-reload (`DirectivesWatcher`) upon external file modification.
- Opening directive files in the system default text editor or viewer across Windows, Linux, and macOS.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any, Callable

logger = logging.getLogger("mind.directives")

DEFAULT_COORDINATOR_DIRECTIVE = """# Primary Coordinator Guidelines
Managed directly via .GEMINI.md.
"""

DEFAULT_WORKER_DIRECTIVE_TEMPLATE = """# Worker Agent Directive ({slot})
Managed directly via .GEMINI.md.
"""


def get_instance_gemini_path(target: str) -> Path | None:
    """Locate the .GEMINI.md file for the given agent target or instance slot.

    Checks:
    1. ~/.local/share/agy-instances/<slot>/.gemini/.GEMINI.md (or GEMINI.md)
    2. Current workspace ./.GEMINI.md or GEMINI.md
    3. Global ~/.gemini/.GEMINI.md
    """
    t = str(target).strip()
    slot_name = ""
    if t.lower() in ("coordinator", "primary", "0"):
        slot_name = "agy1"
    elif t.lower().startswith("agy"):
        slot_name = t.lower()
    else:
        digits = "".join(filter(str.isdigit, t))
        if digits:
            slot_name = f"agy{digits}"
        else:
            slot_name = t

    instances_dir = Path.home() / ".local" / "share" / "agy-instances"
    if instances_dir.exists():
        slot_dir = instances_dir / slot_name / ".gemini"
        if slot_dir.exists():
            for name in (".GEMINI.md", "GEMINI.md"):
                candidate = slot_dir / name
                if candidate.is_file():
                    return candidate
            return slot_dir / ".GEMINI.md"

    cwd = Path.cwd()
    if (cwd / ".GEMINI.md").is_file():
        return cwd / ".GEMINI.md"
    if (cwd / "GEMINI.md").is_file():
        return cwd / "GEMINI.md"

    gemini_home = Path.home() / ".gemini"
    if (gemini_home / ".GEMINI.md").is_file():
        return gemini_home / ".GEMINI.md"
    if (gemini_home / "GEMINI.md").is_file():
        return gemini_home / "GEMINI.md"

    return None


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
    """Resolve target name ('coordinator', 'primary', 'agy1', '1', 'worker-1', etc.) to a file path, prioritizing .GEMINI.md."""
    # First priority: check for instance or workspace .GEMINI.md file
    gemini_file = get_instance_gemini_path(target)
    if gemini_file is not None and gemini_file.exists():
        return gemini_file

    t = str(target).strip().lower()
    if t in ("coordinator", "primary", "0"):
        return get_coordinator_directive_path()

    # Normalize worker identifiers (e.g. 'worker-1', 'worker_2', '1')
    if t.startswith("worker-") or t.startswith("worker_") or (t.startswith("worker") and any(c.isdigit() for c in t)):
        digits = "".join(filter(str.isdigit, t))
        if digits:
            t = f"agy{digits}"
    elif t.isdigit():
        t = f"agy{t}"
    elif not t.startswith("agy") and not t.endswith(".md"):
        t = f"{t}"

    return get_worker_directive_path(t)


def extract_target_from_path(path: Path | str) -> str:
    """Extract agent target ('coordinator', 'agy1', etc.) from directive or .GEMINI.md file path."""
    p = Path(path)
    if p.parent.name == ".gemini" and p.parent.parent.parent.name == "agy-instances":
        return p.parent.parent.name.lower()

    name_lower = p.name.lower()
    if name_lower in ("coordinator.md", "coordinator"):
        return "coordinator"

    stem = p.stem.lower()
    if stem.startswith("worker-") or stem.startswith("worker_") or (stem.startswith("worker") and any(c.isdigit() for c in stem)):
        digits = "".join(filter(str.isdigit, stem))
        if digits:
            return f"agy{digits}"
    if stem.isdigit():
        return f"agy{stem}"
    return stem


def ensure_default_directives(worker_count: int = 5) -> None:
    """Ensure standard coordinator and worker directive files exist on disk."""
    coord_path = get_coordinator_directive_path()
    if not coord_path.exists():
        try:
            coord_path.write_text(DEFAULT_COORDINATOR_DIRECTIVE, encoding="utf-8")
            logger.info("Initialized default coordinator directive at %s", coord_path)
        except Exception as e:
            logger.warning("Could not write default coordinator directive: %s", e)

    count = max(5, int(worker_count))
    for slot_num in range(1, count + 1):
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
    clean_text = content.strip() + "\n"
    path.write_text(clean_text, encoding="utf-8")
    logger.info("Saved persistent directive to %s", path)

    # Update watcher snapshot so internal saves do not trigger redundant external reload events
    global _DEFAULT_WATCHER
    if _DEFAULT_WATCHER is not None:
        _DEFAULT_WATCHER.record_internal_save(path, clean_text.strip())

    return path


def open_directive_in_editor(target: str) -> Path:
    """Open the directive file in the system default text editor or viewer.

    Cross-platform strategy:
    - Windows: `os.startfile(path)`
    - macOS: `open <path>`
    - Linux: `xdg-open <path>`
    - Fallback: `$EDITOR` environment variable or notepad.exe / nano.
    """
    ensure_default_directives()
    path = resolve_directive_path(target)

    # 1. Windows: native shell association
    if sys.platform == "win32":
        try:
            os.startfile(str(path))
            return path
        except Exception:
            pass

    # 2. macOS: native launch services
    if sys.platform == "darwin":
        try:
            subprocess.Popen(["open", str(path)])
            return path
        except Exception:
            pass

    # 3. Linux/POSIX: xdg-open
    if sys.platform.startswith("linux"):
        try:
            subprocess.Popen(["xdg-open", str(path)])
            return path
        except Exception:
            pass

    # 4. Fallback to $EDITOR or default platform editor
    editor = os.environ.get("EDITOR") or ("notepad.exe" if sys.platform == "win32" else "nano")
    try:
        subprocess.Popen([editor, str(path)])
    except Exception as e:
        logger.warning("Could not open editor for %s: %s", path, e)
    return path


# ── Externalized Directives Hot-Reload Watcher ──────────────────────────

class DirectivesWatcher:
    """Lightweight event-driven watcher for directives in ~/.mind/directives/.

    Monitors `coordinator.md` and `workers/*.md` for external file modifications
    and triggers instant callbacks for hot-reloading without CPU-intensive polling.
    """

    def __init__(
        self,
        directives_dir: Path | None = None,
        poll_interval: float = 0.5,
    ) -> None:
        self._directives_dir = directives_dir or get_directives_dir()
        self._poll_interval = max(0.1, float(poll_interval))
        self._file_mtimes: dict[Path, int] = {}
        self._file_contents: dict[Path, str] = {}
        self._listeners: list[Callable[[str, Path, str], None]] = []

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        self._snapshot_existing_files()

    @property
    def directives_dir(self) -> Path:
        return self._directives_dir

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def _snapshot_existing_files(self) -> None:
        """Record initial mtime and content snapshots without notifying listeners."""
        files = self._list_directive_files()
        with self._lock:
            for f in files:
                try:
                    st = f.stat()
                    self._file_mtimes[f] = st.st_mtime_ns
                    self._file_contents[f] = f.read_text(encoding="utf-8", errors="ignore").strip()
                except Exception:
                    pass

    def _list_directive_files(self) -> list[Path]:
        """List all tracked markdown files in the directives and instance .gemini directories."""
        files: list[Path] = []
        if self._directives_dir.exists():
            try:
                for p in self._directives_dir.glob("*.md"):
                    if p.is_file():
                        files.append(p)
                workers_dir = self._directives_dir / "workers"
                if workers_dir.exists():
                    for p in workers_dir.glob("*.md"):
                        if p.is_file():
                            files.append(p)
            except Exception:
                pass

        instances_dir = Path.home() / ".local" / "share" / "agy-instances"
        if instances_dir.exists():
            try:
                for inst in instances_dir.iterdir():
                    if inst.is_dir():
                        gemini_dir = inst / ".gemini"
                        if gemini_dir.is_dir():
                            for f in gemini_dir.glob("*.md"):
                                if f.is_file() and f not in files:
                                    files.append(f)
            except Exception:
                pass
        return sorted(files)

    def record_internal_save(self, path: Path, content: str) -> None:
        """Record an in-app save so subsequent checks do not emit duplicate reload events."""
        with self._lock:
            try:
                if path.exists():
                    self._file_mtimes[path] = path.stat().st_mtime_ns
                self._file_contents[path] = content.strip()
            except Exception:
                pass

    def add_listener(self, callback: Callable[[str, Path, str], None]) -> None:
        """Register a callback invoked when a directive file changes externally."""
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[str, Path, str], None]) -> None:
        """Unregister a previously added listener."""
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def check_for_changes(self) -> list[tuple[str, Path, str]]:
        """Inspect tracked files and return list of (target, path, new_content) for any changes.

        Notifies all registered listeners for each changed file.
        """
        changed: list[tuple[str, Path, str]] = []
        files = self._list_directive_files()

        with self._lock:
            for f in files:
                try:
                    st = f.stat()
                    current_mtime = st.st_mtime_ns
                    last_mtime = self._file_mtimes.get(f)

                    if last_mtime is None or current_mtime != last_mtime:
                        content = f.read_text(encoding="utf-8", errors="ignore").strip()
                        last_content = self._file_contents.get(f)

                        self._file_mtimes[f] = current_mtime
                        if last_content is None or last_content != content:
                            self._file_contents[f] = content
                            target = extract_target_from_path(f)
                            changed.append((target, f, content))
                except Exception as e:
                    logger.debug("Error checking file %s for changes: %s", f, e)

            # Clean up deleted files from tracking
            tracked = list(self._file_mtimes.keys())
            for f in tracked:
                if not f.exists():
                    self._file_mtimes.pop(f, None)
                    self._file_contents.pop(f, None)

        if changed:
            with self._lock:
                listeners = list(self._listeners)
            for target, path, content in changed:
                logger.info("Hot-reloading directive for '%s' from %s", target, path)
                for listener in listeners:
                    try:
                        listener(target, path, content)
                    except Exception as e:
                        logger.error("Error in directive hot-reload listener: %s", e)

        return changed

    def start(self) -> None:
        """Start the background monitoring thread."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="DirectivesHotReloadWatcher",
                daemon=True,
            )
            self._thread.start()
            logger.info("DirectivesWatcher started for %s", self._directives_dir)

    def stop(self) -> None:
        """Stop the background monitoring thread cleanly."""
        self._stop_event.set()
        with self._lock:
            thread = self._thread
            self._thread = None
        if thread and thread.is_alive():
            thread.join(timeout=1.0)
            logger.info("DirectivesWatcher stopped.")

    def _run_loop(self) -> None:
        """Background monitoring loop."""
        while not self._stop_event.is_set():
            try:
                self.check_for_changes()
            except Exception as e:
                logger.debug("Exception in DirectivesWatcher check loop: %s", e)
            self._stop_event.wait(self._poll_interval)


# ── Global Singleton Watcher Management ────────────────────────────────

_DEFAULT_WATCHER: DirectivesWatcher | None = None
_WATCHER_LOCK = threading.Lock()


def get_directives_watcher(poll_interval: float = 0.5) -> DirectivesWatcher:
    """Get or initialize the global DirectivesWatcher singleton."""
    global _DEFAULT_WATCHER
    with _WATCHER_LOCK:
        if _DEFAULT_WATCHER is None:
            _DEFAULT_WATCHER = DirectivesWatcher(poll_interval=poll_interval)
        return _DEFAULT_WATCHER


def start_directives_watcher(
    poll_interval: float = 0.5,
    on_change: Callable[[str, Path, str], None] | None = None,
) -> DirectivesWatcher:
    """Start the global directives watcher, optionally registering an initial callback."""
    watcher = get_directives_watcher(poll_interval=poll_interval)
    if on_change:
        watcher.add_listener(on_change)
    watcher.start()
    return watcher


def stop_directives_watcher() -> None:
    """Stop and clear the global directives watcher singleton."""
    global _DEFAULT_WATCHER
    with _WATCHER_LOCK:
        if _DEFAULT_WATCHER is not None:
            _DEFAULT_WATCHER.stop()
            _DEFAULT_WATCHER = None


def add_directive_change_listener(callback: Callable[[str, Path, str], None]) -> None:
    """Register a global callback for directive file modifications."""
    get_directives_watcher().add_listener(callback)


def remove_directive_change_listener(callback: Callable[[str, Path, str], None]) -> None:
    """Unregister a global callback for directive file modifications."""
    get_directives_watcher().remove_listener(callback)
