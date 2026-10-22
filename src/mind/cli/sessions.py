"""Session Management & Cleanup CLI for mind.

Provides commands and utilities for:
1. Listing all persisted multi-agent orchestration sessions with activity telemetry.
2. Cleaning up inactive, stale, or old temporary sessions.
3. Creating new persisted sessions from the command line.
4. Deleting individual sessions by name.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from mind.core.session_storage import (
    SessionRecord,
    delete_session,
    get_default_sessions_path,
    get_session,
    load_all_sessions,
    save_session,
)


def _relative_time(dt: datetime) -> str:
    """Format datetime into human-friendly relative duration."""
    delta = datetime.now() - dt
    seconds = int(delta.total_seconds())
    if seconds < 0 or seconds < 60:
        return "just now"
    if seconds < 3600:
        mins = seconds // 60
        return f"{mins}m ago"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours}h ago"
    days = seconds // 86400
    return f"{days}d ago"


def list_sessions_cli(as_json: bool = False) -> None:
    """Print all persisted sessions in a formatted table or JSON."""
    sessions = load_all_sessions()

    if as_json:
        data = [s.to_dict() for s in sessions]
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    console = Console()
    table = Table(
        title="🧠  mind sessions — Persisted Multi-Agent Orchestration Sessions",
        header_style="bold #7aa2f7",
        border_style="#3b4261",
        box=None,
        show_edge=True,
    )

    table.add_column("Session Name", style="bold #7dcfff", width=18)
    table.add_column("Agents", justify="center", width=8)
    table.add_column("Status", justify="center", width=12)
    table.add_column("Steps", justify="right", width=8)
    table.add_column("Tasks", justify="right", width=8)
    table.add_column("Created", style="dim", width=12)
    table.add_column("Last Active", style="dim #e0af68", width=12)
    table.add_column("Session Goal", style="italic #c0caf5")

    if not sessions:
        console.print("[dim]No sessions found. Run 'mind new <name>' or 'mind sessions new <name>' to create one.[/dim]")
        return

    for s in sessions:
        status_badge = "[bold #9ece6a]● Active[/]" if s.active else "[dim #565f89]○ Archived[/]"
        created_str = _relative_time(s.created_at)
        active_str = _relative_time(s.last_activity)
        goal_str = s.goal or "[dim]General workspace[/dim]"

        table.add_row(
            s.name,
            str(s.agent_count),
            status_badge,
            str(s.total_steps),
            str(s.total_interactions),
            created_str,
            active_str,
            goal_str,
        )

    console.print()
    console.print(table)
    console.print(f"\n[dim]Storage path: {get_default_sessions_path()}[/dim]\n")


def clean_sessions_cli(
    older_than_days: int = 7,
    clean_all: bool = False,
    as_json: bool = False,
) -> int:
    """Clean up stale or old sessions from persistent storage."""
    sessions = load_all_sessions()
    now = datetime.now()
    threshold = now - timedelta(days=older_than_days)

    cleaned_names: list[str] = []

    for s in list(sessions):
        should_clean = False
        if clean_all:
            # Clean everything except 'default'
            if s.name != "default":
                should_clean = True
        else:
            # Clean if archived or older than threshold and not default
            if s.name != "default":
                if not s.active or (s.last_activity < threshold):
                    should_clean = True

        if should_clean:
            if delete_session(s.name):
                cleaned_names.append(s.name)

    if as_json:
        data = {
            "cleaned_count": len(cleaned_names),
            "cleaned_sessions": cleaned_names,
            "threshold_days": older_than_days,
            "clean_all": clean_all,
        }
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return len(cleaned_names)

    console = Console()
    if cleaned_names:
        console.print(f"[bold green]✓ Successfully cleaned {len(cleaned_names)} sessions:[/]")
        for name in cleaned_names:
            console.print(f"  [dim]- {name}[/dim]")
    else:
        console.print("[dim]No sessions matched cleanup criteria (all sessions are active and recent).[/dim]")

    return len(cleaned_names)


def delete_session_cli(name: str) -> bool:
    """Delete an individual session by name."""
    console = Console()
    existing = get_session(name)
    if not existing:
        console.print(f"[bold red]Error:[/] Session '{name}' does not exist.")
        return False

    success = delete_session(name)
    if success:
        console.print(f"[bold green]✓ Session '{name}' deleted successfully.[/]")
    else:
        console.print(f"[bold red]Error:[/] Could not delete session '{name}'.")
    return success


def create_session_cli(name: str, agent_count: int = 3, goal: str = "") -> SessionRecord:
    """Create a new session record and persist it."""
    console = Console()
    existing = get_session(name)
    if existing:
        console.print(f"[bold yellow]Warning:[/] Session '{name}' already exists. Updating record.")

    record = SessionRecord(
        name=name,
        created_at=datetime.now(),
        last_activity=datetime.now(),
        agent_count=agent_count,
        goal=goal,
        active=True,
    )
    saved = save_session(record)
    console.print(f"[bold green]✓ Session '{saved.name}' created with {saved.agent_count} agents.[/]")
    return saved
