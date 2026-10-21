"""Comprehensive unit and integration test suite for the Accounts Quota & Usage Monitor Engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

from click.testing import CliRunner
import pytest
from rich.table import Table

from mind.cli.main import main
from mind.core.auth.models import TokenStatus
from mind.core.usage_monitor import (
    QuotaStatus,
    SlotQuotaUsage,
    UsageMonitor,
    get_quota_ansi_code,
    get_quota_color_tag,
    parse_timestamp_safe,
    render_colored_bar,
    render_progress_bar,
    render_rich_bar,
)


def test_render_progress_bar_exact_formatting() -> None:
    """Test progress bar generation matches required format [████████░░] 80%."""
    # 80% with width 10: 8 filled blocks and 2 empty blocks
    assert render_progress_bar(80.0, width=10) == "[████████░░] 80%"
    assert render_progress_bar(100.0, width=10) == "[██████████] 100%"
    assert render_progress_bar(0.0, width=10) == "[░░░░░░░░░░] 0%"
    assert render_progress_bar(50.0, width=10) == "[█████░░░░░] 50%"
    assert render_progress_bar(10.0, width=10) == "[█░░░░░░░░░] 10%"
    assert render_progress_bar(90.0, width=10) == "[█████████░] 90%"


def test_render_progress_bar_clamping_and_custom_width() -> None:
    """Test progress bar clamps values out of bounds and honors custom parameters."""
    assert render_progress_bar(-15.0, width=10) == "[░░░░░░░░░░] 0%"
    assert render_progress_bar(150.0, width=10) == "[██████████] 100%"

    # Custom width 20 (80% of 20 = 16 filled)
    bar20 = render_progress_bar(80.0, width=20, show_percentage=False)
    assert bar20 == f"[{'█' * 16}{'░' * 4}]"


def test_color_indicators_and_tags() -> None:
    """Test semantic color indicators for normal, warning, and throttled states."""
    # Tags
    assert get_quota_color_tag(QuotaStatus.NORMAL) == "green"
    assert get_quota_color_tag(QuotaStatus.WARNING) == "yellow"
    assert get_quota_color_tag(QuotaStatus.THROTTLED) == "red"

    # ANSI codes
    start_green, reset = get_quota_ansi_code(QuotaStatus.NORMAL)
    assert "\033[92m" in start_green
    assert reset == "\033[0m"

    start_red, _ = get_quota_ansi_code(QuotaStatus.THROTTLED)
    assert "\033[91m" in start_red

    start_yellow, _ = get_quota_ansi_code(QuotaStatus.WARNING)
    assert "\033[93m" in start_yellow


def test_render_colored_bar_and_rich_bar() -> None:
    """Test render_colored_bar modes and render_rich_bar output."""
    rich_str = render_colored_bar(80.0, QuotaStatus.NORMAL, width=10, mode="rich")
    assert rich_str == "[green][████████░░] 80%[/green]"

    ansi_str = render_colored_bar(80.0, QuotaStatus.WARNING, width=10, mode="ansi")
    assert "\033[93m" in ansi_str and "[████████░░] 80%" in ansi_str

    plain_str = render_colored_bar(80.0, QuotaStatus.THROTTLED, width=10, mode="plain")
    assert plain_str == "[████████░░] 80%"

    rich_text = render_rich_bar(80.0, QuotaStatus.THROTTLED, width=10)
    assert rich_text.plain == "[████████░░] 80%"
    assert rich_text.style == "red"


def test_parse_timestamp_safe() -> None:
    """Test timestamp parser across various formats and edge cases."""
    # ISO strings with variable precision
    dt1 = parse_timestamp_safe("2026-10-21 18:30:00.1234567+00:00")
    assert dt1 is not None
    assert dt1.year == 2026 and dt1.month == 10 and dt1.day == 21

    dt2 = parse_timestamp_safe("2026-10-21T14:20:00Z")
    assert dt2 is not None
    assert dt2.hour == 14

    # Millisecond unix epoch
    dt3 = parse_timestamp_safe(1792603847609)
    assert dt3 is not None
    assert dt3.year == 2026

    # Empty / placeholder dates
    assert parse_timestamp_safe("0001-01-01 00:00:00+00:00") is None
    assert parse_timestamp_safe("") is None
    assert parse_timestamp_safe(None) is None
    assert parse_timestamp_safe("invalid-date-string") is None


@pytest.fixture
def isolated_gemini_env(tmp_path: Path) -> tuple[Path, Path]:
    """Create a temporary mock ~/.gemini environment with instances and tokens."""
    instances_dir = tmp_path / "instances"
    tokens_dir = tmp_path / "tokens"
    instances_dir.mkdir(parents=True)
    tokens_dir.mkdir(parents=True)
    return instances_dir, tokens_dir


def test_slot_usage_calculation(isolated_gemini_env: tuple[Path, Path]) -> None:
    """Test accurate hourly and weekly quota calculation with mock DB and history logs."""
    instances_dir, tokens_dir = isolated_gemini_env

    slot_dir = instances_dir / "agy1" / ".gemini" / "antigravity-cli"
    slot_dir.mkdir(parents=True)

    # 1. Create mock token
    token_file = tokens_dir / "agy1.token"
    token_file.write_text('{"token": {"id_token": "mock.jwt.token"}, "email": "test@example.com"}', encoding="utf-8")

    # 2. Reference point in time
    ref_time = datetime(2026, 10, 21, 15, 0, 0, tzinfo=timezone.utc)

    # 3. Create conversation_summaries.db
    db_file = slot_dir / "conversation_summaries.db"
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE conversation_summaries (
            conversation_id text PRIMARY KEY,
            title text,
            step_count integer,
            last_modified_time datetime,
            last_user_input_time datetime,
            status text
        )
        """
    )
    # Conv 1: 30 minutes ago (in current hour) -> 12 steps
    cur.execute(
        "INSERT INTO conversation_summaries VALUES (?, ?, ?, ?, ?, ?)",
        (
            "conv-1",
            "Task Alpha",
            12,
            (ref_time - timedelta(minutes=30)).isoformat(),
            (ref_time - timedelta(minutes=30)).isoformat(),
            "CASCADE_RUN_STATUS_IDLE",
        ),
    )
    # Conv 2: 2 days ago (in current week) -> 20 steps
    cur.execute(
        "INSERT INTO conversation_summaries VALUES (?, ?, ?, ?, ?, ?)",
        (
            "conv-2",
            "Task Beta",
            20,
            (ref_time - timedelta(days=2)).isoformat(),
            (ref_time - timedelta(days=2)).isoformat(),
            "CASCADE_RUN_STATUS_IDLE",
        ),
    )
    # Conv 3: 10 days ago (outside weekly window) -> 50 steps
    cur.execute(
        "INSERT INTO conversation_summaries VALUES (?, ?, ?, ?, ?, ?)",
        (
            "conv-3",
            "Task Gamma",
            50,
            (ref_time - timedelta(days=10)).isoformat(),
            (ref_time - timedelta(days=10)).isoformat(),
            "CASCADE_RUN_STATUS_IDLE",
        ),
    )
    conn.commit()
    conn.close()

    # 4. Create history.jsonl
    hist_file = slot_dir / "history.jsonl"
    hist_events = [
        {"timestamp": int((ref_time - timedelta(minutes=15)).timestamp() * 1000), "type": "command"},
        {"timestamp": int((ref_time - timedelta(minutes=10)).timestamp() * 1000), "type": "command"},
        {"timestamp": int((ref_time - timedelta(days=1)).timestamp() * 1000), "type": "command"},
    ]
    with open(hist_file, "w", encoding="utf-8") as f:
        for ev in hist_events:
            f.write(json.dumps(ev) + "\n")

    monitor = UsageMonitor(
        instances_dir=instances_dir,
        tokens_dir=tokens_dir,
        default_hourly_limit=60,
        default_weekly_limit=1000,
    )

    usage = monitor.get_slot_usage("agy1", reference_time=ref_time)

    assert usage.slot == "agy1"
    assert usage.email == "test@example.com"
    assert usage.total_conversations == 3
    assert usage.total_steps == 82  # 12 + 20 + 50

    # Hourly: 12 steps from conv-1 (greater than 2 history events)
    assert usage.hourly_used == 12
    assert usage.hourly_remaining == 48  # 60 - 12
    assert usage.hourly_percent == 20.0
    assert usage.hourly_remaining_percent == 80.0

    # Weekly: 12 + 20 = 32 steps (greater than 3 history events)
    assert usage.weekly_used == 32
    assert usage.weekly_remaining == 968  # 1000 - 32
    assert usage.weekly_percent == 3.2
    assert usage.weekly_remaining_percent == 96.8

    # Status should be NORMAL (plentiful)
    assert usage.status == QuotaStatus.NORMAL
    assert not usage.is_throttled
    assert usage.progress_bar == "[████████░░] 80%"
    assert "[green]" in usage.colored_progress_bar

    # to_dict verification
    d = usage.to_dict()
    assert d["slot"] == "agy1"
    assert d["hourly_remaining"] == 48
    assert d["status"] == "normal"


def test_warning_and_throttled_states(isolated_gemini_env: tuple[Path, Path]) -> None:
    """Test warning and throttled state detection on quota exhaustion or expired token."""
    instances_dir, tokens_dir = isolated_gemini_env
    ref_time = datetime(2026, 10, 21, 12, 0, 0, tzinfo=timezone.utc)

    # Slot 1: Warning (hourly remaining is <= 20%)
    slot1_dir = instances_dir / "agy1" / ".gemini" / "antigravity-cli"
    slot1_dir.mkdir(parents=True)
    db1 = slot1_dir / "conversation_summaries.db"
    conn = sqlite3.connect(str(db1))
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE conversation_summaries (conversation_id text, title text, step_count integer, last_modified_time datetime, last_user_input_time datetime, status text)"
    )
    # Used 52 out of 60 -> remaining 8 (13.3% remaining <= 20% warning threshold)
    cur.execute(
        "INSERT INTO conversation_summaries VALUES (?, ?, ?, ?, ?, ?)",
        ("c1", "Task", 52, ref_time.isoformat(), ref_time.isoformat(), "IDLE"),
    )
    conn.commit()
    conn.close()

    # Slot 2: Throttled (hourly remaining is 0)
    slot2_dir = instances_dir / "agy2" / ".gemini" / "antigravity-cli"
    slot2_dir.mkdir(parents=True)
    db2 = slot2_dir / "conversation_summaries.db"
    conn = sqlite3.connect(str(db2))
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE conversation_summaries (conversation_id text, title text, step_count integer, last_modified_time datetime, last_user_input_time datetime, status text)"
    )
    cur.execute(
        "INSERT INTO conversation_summaries VALUES (?, ?, ?, ?, ?, ?)",
        ("c2", "Task", 70, ref_time.isoformat(), ref_time.isoformat(), "IDLE"),
    )
    conn.commit()
    conn.close()

    # Slot 3: Throttled via expired token
    token3 = tokens_dir / "agy3.token"
    # Construct a valid JSON token payload with past exp
    past_epoch = int((ref_time - timedelta(hours=2)).timestamp())
    token3.write_text(f'{{"token": {{"access_token": "ya29.test", "expires_at": {past_epoch}}}}}', encoding="utf-8")

    monitor = UsageMonitor(
        instances_dir=instances_dir,
        tokens_dir=tokens_dir,
        default_hourly_limit=60,
        warning_threshold_percent=20.0,
    )

    u1 = monitor.get_slot_usage("agy1", reference_time=ref_time)
    assert u1.status == QuotaStatus.WARNING
    assert not u1.is_throttled
    assert "[yellow]" in u1.colored_progress_bar

    u2 = monitor.get_slot_usage("agy2", reference_time=ref_time)
    assert u2.status == QuotaStatus.THROTTLED
    assert u2.is_throttled
    assert u2.hourly_remaining == 0
    assert "[red]" in u2.colored_progress_bar

    u3 = monitor.get_slot_usage("agy3", reference_time=ref_time)
    assert u3.status == QuotaStatus.THROTTLED
    assert u3.is_throttled
    assert "[red]" in u3.colored_progress_bar


def test_get_all_slots_usage_and_summary(isolated_gemini_env: tuple[Path, Path]) -> None:
    """Test multi-slot discovery and aggregated summary generation."""
    instances_dir, tokens_dir = isolated_gemini_env

    for s in ["agy1", "agy2", "agy3"]:
        p = instances_dir / s / ".gemini" / "antigravity-cli"
        p.mkdir(parents=True)

    monitor = UsageMonitor(instances_dir=instances_dir, tokens_dir=tokens_dir)
    all_usage = monitor.get_all_slots_usage()

    assert len(all_usage) == 3
    assert [u.slot for u in all_usage] == ["agy1", "agy2", "agy3"]

    summary = monitor.to_dict_summary(all_usage)
    assert summary["summary"]["total_slots"] == 3
    assert "slots" in summary

    # Rich table creation
    table = monitor.create_rich_table(all_usage)
    assert isinstance(table, Table)
    assert table.row_count == 3


def test_cli_usage_commands() -> None:
    """Test Click CLI entrypoint for 'mind usage' and '-u' flag."""
    runner = CliRunner()

    # mind usage --help
    res_help = runner.invoke(main, ["usage", "--help"])
    assert res_help.exit_code == 0
    assert "--slot" in res_help.output
    assert "--json" in res_help.output

    # mind usage --json
    res_json = runner.invoke(main, ["usage", "--json"])
    assert res_json.exit_code == 0
    data = json.loads(res_json.output)
    assert "summary" in data
    assert "slots" in data

    # mind -u
    res_u = runner.invoke(main, ["-u"])
    assert res_u.exit_code == 0
    assert "Accounts Quota & Usage Monitor" in res_u.output
