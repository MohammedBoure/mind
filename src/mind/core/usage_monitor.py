"""Accounts Quota & Usage Monitor Engine for mind.

Tracks and monitors Antigravity worker slots (agy1 .. agyN) by:
1. Inspecting authentication tokens, account emails, validity, and expiration windows.
2. Querying conversation SQLite databases (conversation_summaries.db, conversations/*.db)
   and session interaction logs (history.jsonl).
3. Computing hourly remaining (Hourly Remaining) and weekly remaining (Weekly Remaining)
   quotas, usage counts, and consumption percentages across temporal windows.
4. Generating high-precision graphic progress bars (e.g. `[████████░░] 80%`) with
   semantic color coding (Green for plentiful quota, Yellow for warnings, Red for throttled/depleted).
5. Providing standalone CLI execution and programmatic API integration for TUI / MCP tools.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any, Iterable

from rich.box import ROUNDED
from rich.console import Console
from rich.table import Table
from rich.text import Text

from mind.core.agent_discovery import (
    discover_system_agents,
    get_agys_instances_dir,
    get_slot_instance_dir,
    get_slot_instance_token_path,
)
from mind.core.auth.models import TokenStatus
from mind.core.auth.validator import AuthValidator

logger = logging.getLogger("mind.core.usage_monitor")


class QuotaStatus(str, Enum):
    """Semantic status of an account's quota and operational health."""

    NORMAL = "normal"        # Plentiful quota (Green)
    WARNING = "warning"      # Approaching limit (Yellow)
    THROTTLED = "throttled"  # Depleted / Throttled / Expired (Red)


@dataclass
class SlotQuotaUsage:
    """Comprehensive quota consumption and operational statistics for an agy slot."""

    slot: str
    account: str | None = None
    email: str | None = None
    token_status: str = TokenStatus.EMPTY.value
    token_expires_at: datetime | None = None
    token_remaining_seconds: float = 0.0

    # Hourly consumption (last 3600 seconds)
    hourly_used: int = 0
    hourly_limit: int = 60
    hourly_remaining: int = 60
    hourly_percent: float = 0.0             # Percentage of limit consumed (0..100)
    hourly_remaining_percent: float = 100.0 # Percentage of limit remaining (0..100)

    # Weekly consumption (last 7 days)
    weekly_used: int = 0
    weekly_limit: int = 1000
    weekly_remaining: int = 1000
    weekly_percent: float = 0.0             # Percentage of limit consumed (0..100)
    weekly_remaining_percent: float = 100.0 # Percentage of limit remaining (0..100)

    # Aggregate counters
    total_conversations: int = 0
    total_steps: int = 0
    last_activity_time: datetime | None = None

    # Status & throttling
    status: QuotaStatus = QuotaStatus.NORMAL
    is_throttled: bool = False
    throttle_reason: str | None = None

    # Graphic progress bars
    progress_bar: str = ""
    colored_progress_bar: str = ""
    hourly_bar: str = ""
    weekly_bar: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert stats to a serializable dictionary for MCP tools or JSON export."""
        data = asdict(self)
        data["status"] = self.status.value
        data["token_expires_at"] = (
            self.token_expires_at.isoformat() if self.token_expires_at else None
        )
        data["last_activity_time"] = (
            self.last_activity_time.isoformat() if self.last_activity_time else None
        )
        return data


def render_progress_bar(
    percentage: float,
    width: int = 10,
    fill_char: str = "█",
    empty_char: str = "░",
    show_percentage: bool = True,
) -> str:
    """Generate high-precision graphic progress bar.

    Example:
        render_progress_bar(80.0, width=10) -> "[████████░░] 80%"
    """
    pct = max(0.0, min(100.0, float(percentage)))
    filled_count = int(round((pct / 100.0) * width))
    filled_count = max(0, min(width, filled_count))
    empty_count = width - filled_count
    bar = f"[{fill_char * filled_count}{empty_char * empty_count}]"
    if show_percentage:
        return f"{bar} {int(round(pct))}%"
    return bar


def get_quota_color_tag(status: QuotaStatus | str) -> str:
    """Return the Rich color tag associated with the quota status."""
    st = status.value if isinstance(status, QuotaStatus) else str(status).lower()
    if st == QuotaStatus.THROTTLED.value:
        return "red"
    if st == QuotaStatus.WARNING.value:
        return "yellow"
    return "green"


def get_quota_ansi_code(status: QuotaStatus | str) -> tuple[str, str]:
    """Return the ANSI color code tuple (start_code, reset_code) for terminal printing."""
    st = status.value if isinstance(status, QuotaStatus) else str(status).lower()
    if st == QuotaStatus.THROTTLED.value:
        return ("\033[91m", "\033[0m")  # Bright red
    if st == QuotaStatus.WARNING.value:
        return ("\033[93m", "\033[0m")  # Bright yellow
    return ("\033[92m", "\033[0m")      # Bright green


def render_colored_bar(
    percentage: float,
    status: QuotaStatus | str,
    width: int = 10,
    mode: str = "rich",
) -> str:
    """Render graphic progress bar with semantic color indicators.

    Modes:
        - 'rich': Rich console markup (e.g. `[green][████████░░] 80%[/green]`)
        - 'ansi': Standard ANSI terminal escape sequences
        - 'plain': Unadorned text without formatting
    """
    bar_text = render_progress_bar(percentage, width=width, show_percentage=True)
    if mode == "rich":
        color = get_quota_color_tag(status)
        return f"[{color}]{bar_text}[/{color}]"
    if mode == "ansi":
        start_code, end_code = get_quota_ansi_code(status)
        return f"{start_code}{bar_text}{end_code}"
    return bar_text


def render_rich_bar(
    percentage: float,
    status: QuotaStatus | str,
    width: int = 10,
) -> Text:
    """Return a Rich Text object for TUI widgets and Rich console tables."""
    bar_text = render_progress_bar(percentage, width=width, show_percentage=True)
    color = get_quota_color_tag(status)
    return Text(bar_text, style=color)


def parse_timestamp_safe(val: Any) -> datetime | None:
    """Safely parse various datetime representations into UTC datetimes.

    Supports:
        - ISO-8601 strings with variable subsecond precision and timezone offsets
        - Unix millisecond timestamps (e.g. 1792603847609)
        - Unix second timestamps
        - Python datetime objects
        - Safely ignores placeholder dates (e.g. '0001-01-01 00:00:00+00:00')
    """
    if val is None:
        return None

    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val.astimezone(timezone.utc)

    if isinstance(val, (int, float)):
        # Milliseconds vs seconds detection
        if val > 1e11:
            val = val / 1000.0
        try:
            return datetime.fromtimestamp(val, tz=timezone.utc)
        except Exception:
            return None

    val_str = str(val).strip()
    if not val_str or val_str.startswith("0001-01-01"):
        return None

    # Truncate fractional seconds to 6 digits max for fromisoformat compatibility
    # Pattern matches YYYY-MM-DD[T ]HH:MM:SS(.fraction)?(timezone)?
    m = re.match(r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})(?:\.(\d+))?(.*)$", val_str)
    if m:
        base, frac, tz = m.groups()
        if frac:
            frac = (frac + "000000")[:6]
            val_str = f"{base}.{frac}{tz}"
        else:
            val_str = f"{base}{tz}"

    val_str = val_str.replace(" ", "T")
    try:
        dt = datetime.fromisoformat(val_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    return None


class UsageMonitor:
    """Reads, monitors, and evaluates quota usage across all agy worker slots."""

    def __init__(
        self,
        instances_dir: Path | str | None = None,
        tokens_dir: Path | str | None = None,
        default_hourly_limit: int = 60,
        default_weekly_limit: int = 1000,
        warning_threshold_percent: float = 20.0,
        validator: AuthValidator | None = None,
    ) -> None:
        self.instances_dir = (
            Path(instances_dir)
            if instances_dir
            else Path(os.path.expanduser("~/.gemini/instances"))
        )
        self.tokens_dir = (
            Path(tokens_dir)
            if tokens_dir
            else Path(os.path.expanduser("~/.gemini/tokens"))
        )
        self.default_hourly_limit = default_hourly_limit
        self.default_weekly_limit = default_weekly_limit
        self.warning_threshold_percent = warning_threshold_percent
        self.validator = validator or AuthValidator()

    def _normalize_slot_name(self, slot: str | int) -> str:
        """Normalize slot identifiers (e.g. 1 -> 'agy1', 'agy1' -> 'agy1')."""
        s = str(slot).strip()
        if s.isdigit():
            return f"agy{s}"
        return s

    def _is_custom_environment(self) -> bool:
        """Check if monitor was initialized with custom test or non-default directories."""
        default_instances = Path(os.path.expanduser("~/.gemini/instances"))
        default_tokens = Path(os.path.expanduser("~/.gemini/tokens"))
        try:
            return (
                self.instances_dir.resolve() != default_instances.resolve()
                or self.tokens_dir.resolve() != default_tokens.resolve()
            )
        except Exception:
            return (
                self.instances_dir != default_instances
                or self.tokens_dir != default_tokens
            )

    def _find_token_data(self, slot_name: str) -> bytes | None:
        """Locate and read raw token bytes for a slot from central or instance storage."""
        # 1. Check central token path: self.tokens_dir / f"{slot_name}.token"
        central_token = self.tokens_dir / f"{slot_name}.token"
        if central_token.exists() and central_token.stat().st_size > 0:
            try:
                raw = central_token.read_bytes()
                if raw.strip():
                    return raw
            except Exception as err:
                logger.debug("Failed reading central token %s: %s", central_token, err)

        # 2. Check instance token paths in self.instances_dir
        for inst_tok in [
            self.instances_dir / slot_name / "token.json",
            self.instances_dir / slot_name / ".gemini" / "antigravity-cli" / "antigravity-oauth-token",
            self.instances_dir / slot_name / "antigravity-cli" / "antigravity-oauth-token",
        ]:
            if inst_tok.exists() and inst_tok.stat().st_size > 0:
                try:
                    return inst_tok.read_bytes()
                except Exception as err:
                    logger.debug("Failed reading instance token %s: %s", inst_tok, err)

        # 3. If running in default host environment, inspect agys multi-instance storage
        if not self._is_custom_environment():
            try:
                slot_inst_tok = get_slot_instance_token_path(slot_name)
                if slot_inst_tok.exists() and slot_inst_tok.stat().st_size > 0:
                    return slot_inst_tok.read_bytes()
            except Exception:
                pass

        return None

    def _get_app_data_candidates(self, slot_name: str) -> list[Path]:
        """Return candidate directory paths where Antigravity stores data for this slot."""
        instance_base = self.instances_dir / slot_name
        candidates = [
            instance_base / ".gemini" / "antigravity-cli",
            instance_base / "antigravity-cli",
            instance_base,
        ]

        if not self._is_custom_environment():
            try:
                inst_dir = get_slot_instance_dir(slot_name)
                if inst_dir.exists() and inst_dir != instance_base:
                    candidates.extend([
                        inst_dir / ".gemini" / "antigravity-cli",
                        inst_dir / "antigravity-cli",
                        inst_dir,
                    ])
            except Exception:
                pass

        # For primary slot agy1, also check system central ~/.gemini/antigravity-cli as fallback
        if slot_name == "agy1" and not self._is_custom_environment():
            system_app_data = Path(os.path.expanduser("~/.gemini/antigravity-cli"))
            if system_app_data.exists():
                candidates.append(system_app_data)

        return candidates

    def _read_conversation_summaries(
        self, db_path: Path
    ) -> list[dict[str, Any]]:
        """Read conversation records from conversation_summaries.db."""
        if not db_path.exists() or db_path.stat().st_size == 0:
            return []

        records: list[dict[str, Any]] = []
        conn = None
        try:
            # Connect in read-only mode to prevent database locks
            try:
                uri = f"file:{db_path.as_posix()}?mode=ro"
                conn = sqlite3.connect(uri, uri=True, timeout=2.0)
            except Exception:
                conn = sqlite3.connect(str(db_path), timeout=2.0)

            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                """
                SELECT conversation_id, title, step_count, last_modified_time,
                       last_user_input_time, status
                FROM conversation_summaries
                """
            )
            for row in cur.fetchall():
                records.append(
                    {
                        "conversation_id": row["conversation_id"],
                        "title": row["title"],
                        "step_count": int(row["step_count"] or 0),
                        "last_modified_time": parse_timestamp_safe(row["last_modified_time"]),
                        "last_user_input_time": parse_timestamp_safe(row["last_user_input_time"]),
                        "status": str(row["status"] or ""),
                    }
                )
        except Exception as err:
            logger.debug("Error reading SQLite summaries at %s: %s", db_path, err)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        return records

    def _read_history_log(self, history_path: Path) -> list[dict[str, Any]]:
        """Read interaction events from history.jsonl."""
        if not history_path.exists() or history_path.stat().st_size == 0:
            return []

        events: list[dict[str, Any]] = []
        try:
            with open(history_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line_clean = line.strip()
                    if not line_clean:
                        continue
                    try:
                        data = json.loads(line_clean)
                        if isinstance(data, dict):
                            ts = parse_timestamp_safe(data.get("timestamp"))
                            events.append(
                                {
                                    "timestamp": ts,
                                    "display": data.get("display", ""),
                                    "type": data.get("type", ""),
                                }
                            )
                    except Exception:
                        continue
        except Exception as err:
            logger.debug("Error reading history.jsonl at %s: %s", history_path, err)

        return events

    def get_slot_usage(
        self,
        slot: str | int,
        reference_time: datetime | None = None,
        hourly_limit: int | None = None,
        weekly_limit: int | None = None,
    ) -> SlotQuotaUsage:
        """Calculate quota consumption, remaining balances, and progress bar for a single slot.

        Args:
            slot: Slot identifier (e.g. 'agy1', 1).
            reference_time: Reference point in time (defaults to datetime.now(timezone.utc)).
            hourly_limit: Optional override for hourly quota.
            weekly_limit: Optional override for weekly quota.

        Returns:
            Populated SlotQuotaUsage instance.
        """
        slot_name = self._normalize_slot_name(slot)
        ref_time = reference_time or datetime.now(timezone.utc)
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)

        one_hour_ago = ref_time - timedelta(hours=1)
        one_week_ago = ref_time - timedelta(days=7)

        h_limit = hourly_limit or self.default_hourly_limit
        w_limit = weekly_limit or self.default_weekly_limit

        # 1. Parse Token & Identity Information
        raw_token = self._find_token_data(slot_name)
        email: str | None = None
        account: str | None = None
        token_status = TokenStatus.EMPTY.value
        token_expires_at: datetime | None = None
        token_remaining_secs = 0.0

        if raw_token:
            val_result = self.validator.validate(raw_token)
            token_status = val_result.status.value
            if val_result.claims:
                email = val_result.claims.email
                account = val_result.claims.account or val_result.claims.email
                token_expires_at = val_result.claims.expires_at
                token_remaining_secs = val_result.claims.remaining_seconds
            else:
                email = self.validator.extract_email(raw_token)
                account = email

            # If reference_time is evaluated and token specifies expiration, check temporal validity relative to reference_time
            if token_expires_at:
                if (token_expires_at.timestamp() + self.validator.clock_skew_seconds) < ref_time.timestamp():
                    token_status = TokenStatus.EXPIRED.value
                    token_remaining_secs = 0.0
                else:
                    token_remaining_secs = max(0.0, (token_expires_at - ref_time).total_seconds())

        # 2. Discover and Read Activity Sources
        app_dirs = self._get_app_data_candidates(slot_name)
        conv_records: list[dict[str, Any]] = []
        history_events: list[dict[str, Any]] = []

        for app_dir in app_dirs:
            if not app_dir.exists():
                continue

            # Read conversation_summaries.db
            db_file = app_dir / "conversation_summaries.db"
            if db_file.exists() and not conv_records:
                conv_records = self._read_conversation_summaries(db_file)

            # Read history.jsonl
            hist_file = app_dir / "history.jsonl"
            if hist_file.exists() and not history_events:
                history_events = self._read_history_log(hist_file)

        # 3. Analyze Activity and Compute Quota Consumption
        total_steps = 0
        total_conversations = len(conv_records)
        latest_activity: datetime | None = None
        has_throttled_indicator = False
        throttle_reason: str | None = None

        hourly_steps = 0
        weekly_steps = 0

        for conv in conv_records:
            steps = conv["step_count"]
            total_steps += steps

            status_str = conv["status"].upper()
            if any(term in status_str for term in ["THROTTLED", "RATE_LIMIT", "RESOURCE_EXHAUSTED", "429"]):
                has_throttled_indicator = True
                throttle_reason = f"Conversation flagged: {conv['status']}"

            # Check relevant timestamp (prefer last_user_input_time, fallback to last_modified_time)
            ts = conv["last_user_input_time"] or conv["last_modified_time"]
            if ts:
                if latest_activity is None or ts > latest_activity:
                    latest_activity = ts

                if ts >= one_hour_ago and ts <= ref_time:
                    hourly_steps += steps
                if ts >= one_week_ago and ts <= ref_time:
                    weekly_steps += steps

        # Analyze history events
        hourly_history_count = 0
        weekly_history_count = 0

        for evt in history_events:
            ts = evt["timestamp"]
            if ts:
                if latest_activity is None or ts > latest_activity:
                    latest_activity = ts

                if ts >= one_hour_ago and ts <= ref_time:
                    hourly_history_count += 1
                if ts >= one_week_ago and ts <= ref_time:
                    weekly_history_count += 1

        # Use maximum detected activity to accurately reflect consumption
        hourly_used = max(hourly_steps, hourly_history_count)
        weekly_used = max(weekly_steps, weekly_history_count)

        # 4. Calculate Remaining Quotas & Percentages
        hourly_remaining = max(0, h_limit - hourly_used)
        hourly_percent = (
            min(100.0, (hourly_used / h_limit) * 100.0) if h_limit > 0 else 0.0
        )
        hourly_remaining_percent = max(0.0, 100.0 - hourly_percent)

        weekly_remaining = max(0, w_limit - weekly_used)
        weekly_percent = (
            min(100.0, (weekly_used / w_limit) * 100.0) if w_limit > 0 else 0.0
        )
        weekly_remaining_percent = max(0.0, 100.0 - weekly_percent)

        # 5. Evaluate Operational Status (Green / Yellow / Red)
        is_throttled = False

        if token_status == TokenStatus.EXPIRED.value:
            is_throttled = True
            throttle_reason = "Authentication token expired"
            status = QuotaStatus.THROTTLED
        elif hourly_remaining <= 0:
            is_throttled = True
            throttle_reason = "Hourly quota exhausted (100% consumed)"
            status = QuotaStatus.THROTTLED
        elif weekly_remaining <= 0:
            is_throttled = True
            throttle_reason = "Weekly quota exhausted (100% consumed)"
            status = QuotaStatus.THROTTLED
        elif has_throttled_indicator:
            is_throttled = True
            status = QuotaStatus.THROTTLED
        elif (
            hourly_remaining_percent <= self.warning_threshold_percent
            or weekly_remaining_percent <= self.warning_threshold_percent
        ):
            status = QuotaStatus.WARNING
        else:
            status = QuotaStatus.NORMAL

        # 6. Generate Graphic Progress Bars for Remaining Quota
        # If throttled or depleted, effective remaining percent is 0%
        effective_hourly_remaining = 0.0 if (is_throttled and hourly_remaining <= 0) else hourly_remaining_percent
        effective_weekly_remaining = 0.0 if (is_throttled and weekly_remaining <= 0) else weekly_remaining_percent

        # Primary remaining quota indicator
        if is_throttled:
            primary_remaining_pct = 0.0 if (hourly_remaining <= 0 or weekly_remaining <= 0) else min(hourly_remaining_percent, weekly_remaining_percent)
        else:
            primary_remaining_pct = min(hourly_remaining_percent, weekly_remaining_percent)

        progress_bar = render_progress_bar(primary_remaining_pct, width=10)
        colored_progress_bar = render_colored_bar(
            primary_remaining_pct, status=status, width=10, mode="rich"
        )

        hourly_bar = render_colored_bar(
            effective_hourly_remaining,
            status=status,
            width=10,
            mode="rich",
        )

        weekly_status = (
            QuotaStatus.THROTTLED
            if (is_throttled and weekly_remaining <= 0)
            else (
                QuotaStatus.WARNING
                if effective_weekly_remaining <= self.warning_threshold_percent
                else QuotaStatus.NORMAL
            )
        )
        weekly_bar = render_colored_bar(
            effective_weekly_remaining,
            status=weekly_status,
            width=10,
            mode="rich",
        )

        return SlotQuotaUsage(
            slot=slot_name,
            account=account,
            email=email,
            token_status=token_status,
            token_expires_at=token_expires_at,
            token_remaining_seconds=token_remaining_secs,
            hourly_used=hourly_used,
            hourly_limit=h_limit,
            hourly_remaining=hourly_remaining,
            hourly_percent=round(hourly_percent, 1),
            hourly_remaining_percent=round(hourly_remaining_percent, 1),
            weekly_used=weekly_used,
            weekly_limit=w_limit,
            weekly_remaining=weekly_remaining,
            weekly_percent=round(weekly_percent, 1),
            weekly_remaining_percent=round(weekly_remaining_percent, 1),
            total_conversations=total_conversations,
            total_steps=total_steps,
            last_activity_time=latest_activity,
            status=status,
            is_throttled=is_throttled,
            throttle_reason=throttle_reason,
            progress_bar=progress_bar,
            colored_progress_bar=colored_progress_bar,
            hourly_bar=hourly_bar,
            weekly_bar=weekly_bar,
        )

    def get_all_slots_usage(
        self,
        reference_time: datetime | None = None,
        hourly_limit: int | None = None,
        weekly_limit: int | None = None,
        include_system_agents: bool | None = None,
    ) -> list[SlotQuotaUsage]:
        """Discover all available worker slots and return usage stats for each."""
        slots_found: set[str] = set()

        default_instances = Path(os.path.expanduser("~/.gemini/instances"))
        default_tokens = Path(os.path.expanduser("~/.gemini/tokens"))
        try:
            is_custom_env = (
                self.instances_dir.resolve() != default_instances.resolve()
                or self.tokens_dir.resolve() != default_tokens.resolve()
            )
        except Exception:
            is_custom_env = (
                self.instances_dir != default_instances
                or self.tokens_dir != default_tokens
            )

        should_include_system = (
            include_system_agents
            if include_system_agents is not None
            else (not is_custom_env)
        )

        # 1. Discover via system agent discovery (if permitted)
        if should_include_system:
            for agent in discover_system_agents():
                norm = self._normalize_slot_name(agent)
                if norm.lower() not in ("agy", "agys"):
                    slots_found.add(norm)

            # Discover via agys multi-instance base directory
            agys_base = get_agys_instances_dir()
            if agys_base.exists():
                for p in agys_base.iterdir():
                    if p.is_dir() and re.match(r"^agy\d+$", p.name, re.IGNORECASE):
                        slots_found.add(p.name.lower())

        # 3. Discover via instances directory
        if self.instances_dir.exists():
            for p in self.instances_dir.iterdir():
                if p.is_dir() and re.match(r"^agy\d+$", p.name, re.IGNORECASE):
                    slots_found.add(p.name.lower())

        # 4. Discover via central tokens directory
        if self.tokens_dir.exists():
            for p in self.tokens_dir.glob("*.token"):
                if re.match(r"^agy\d+$", p.stem, re.IGNORECASE):
                    slots_found.add(p.stem.lower())

        # Filter out non-agent tools
        slots_found = {s for s in slots_found if s.lower() not in ("agy", "agys")}

        if not slots_found:
            slots_found = {"agy1", "agy2", "agy3", "agy4"}

        def _sort_key(name: str) -> tuple[int, str]:
            m = re.search(r"\d+", name)
            return (int(m.group()) if m else 9999, name)

        results: list[SlotQuotaUsage] = []
        for slot in sorted(slots_found, key=_sort_key):
            usage = self.get_slot_usage(
                slot,
                reference_time=reference_time,
                hourly_limit=hourly_limit,
                weekly_limit=weekly_limit,
            )
            results.append(usage)

        return results

    def create_rich_table(
        self,
        slots: Iterable[SlotQuotaUsage],
        title: str = "Accounts Quota & Usage Monitor",
    ) -> Table:
        """Generate a styled Rich Table presenting quota metrics for all slots."""
        table = Table(
            title=f"[bold cyan]{title}[/bold cyan]",
            title_justify="center",
            header_style="bold magenta",
            box=ROUNDED,
            show_edge=True,
            show_lines=False,
        )

        table.add_column("Slot", style="bold cyan", justify="left", no_wrap=True, min_width=6)
        table.add_column("Account / Email", style="white", justify="left", min_width=18, max_width=32)
        table.add_column("Status", justify="center", no_wrap=True, min_width=12)
        table.add_column("Hourly Rem.", justify="right", no_wrap=True, min_width=11)
        table.add_column("Hourly Bar", justify="left", no_wrap=True, min_width=16)
        table.add_column("Weekly Rem.", justify="right", no_wrap=True, min_width=11)
        table.add_column("Weekly Bar", justify="left", no_wrap=True, min_width=16)
        table.add_column("Last Active", style="dim", justify="right", no_wrap=True, min_width=10)

        for s in slots:
            # Status badge
            if s.status == QuotaStatus.THROTTLED:
                status_badge = "[bold red]x Throttled[/bold red]"
            elif s.status == QuotaStatus.WARNING:
                status_badge = "[bold yellow]! Warning[/bold yellow]"
            else:
                status_badge = "[bold green]● Normal[/bold green]"

            # Hourly bar
            h_bar = s.hourly_bar or render_colored_bar(
                s.hourly_remaining_percent, status=s.status, width=10, mode="rich"
            )

            # Weekly bar
            w_status = (
                QuotaStatus.WARNING
                if s.weekly_remaining_percent <= self.warning_threshold_percent
                else QuotaStatus.NORMAL
            )
            if s.weekly_remaining <= 0 or (s.is_throttled and s.weekly_remaining <= 0):
                w_status = QuotaStatus.THROTTLED
            w_bar = s.weekly_bar or render_colored_bar(
                s.weekly_remaining_percent, status=w_status, width=10, mode="rich"
            )

            # Relative activity
            last_act_str = "-"
            if s.last_activity_time:
                now = datetime.now(timezone.utc)
                diff = now - s.last_activity_time
                if diff.total_seconds() < 60:
                    last_act_str = "just now"
                elif diff.total_seconds() < 3600:
                    last_act_str = f"{int(diff.total_seconds() // 60)}m ago"
                elif diff.total_seconds() < 86400:
                    last_act_str = f"{int(diff.total_seconds() // 3600)}h ago"
                else:
                    last_act_str = f"{int(diff.total_seconds() // 86400)}d ago"

            acc_display = s.email or s.account or "[dim]Unauthenticated[/dim]"

            table.add_row(
                s.slot,
                acc_display,
                status_badge,
                f"{s.hourly_remaining}/{s.hourly_limit}",
                h_bar,
                f"{s.weekly_remaining}/{s.weekly_limit}",
                w_bar,
                last_act_str,
            )

        return table

    def to_dict_summary(self, slots: Iterable[SlotQuotaUsage]) -> dict[str, Any]:
        """Produce an aggregated dictionary summary of multiple slots."""
        slots_list = list(slots)
        total_slots = len(slots_list)
        throttled_count = sum(1 for s in slots_list if s.is_throttled)
        warning_count = sum(1 for s in slots_list if s.status == QuotaStatus.WARNING)
        normal_count = sum(1 for s in slots_list if s.status == QuotaStatus.NORMAL)

        return {
            "summary": {
                "total_slots": total_slots,
                "normal": normal_count,
                "warning": warning_count,
                "throttled": throttled_count,
                "total_steps": sum(s.total_steps for s in slots_list),
            },
            "slots": [s.to_dict() for s in slots_list],
        }


def print_usage_cli(
    slot: str | None = None,
    as_json: bool = False,
    hourly_limit: int | None = None,
    weekly_limit: int | None = None,
) -> None:
    """Print quota and usage monitoring table or JSON to standard output."""
    monitor = UsageMonitor()
    if slot:
        slots_usage = [
            monitor.get_slot_usage(
                slot, hourly_limit=hourly_limit, weekly_limit=weekly_limit
            )
        ]
    else:
        slots_usage = monitor.get_all_slots_usage(
            hourly_limit=hourly_limit, weekly_limit=weekly_limit
        )

    if as_json:
        summary_dict = monitor.to_dict_summary(slots_usage)
        print(json.dumps(summary_dict, indent=2))
        return

    console = Console()
    table = monitor.create_rich_table(slots_usage)
    console.print()
    console.print(table)
    console.print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Accounts Quota & Usage Monitor Engine for Antigravity slots."
    )
    parser.add_argument(
        "--slot", "-s", type=str, default=None, help="Specific slot to query (e.g. agy1)"
    )
    parser.add_argument(
        "--json", "-j", action="store_true", help="Output results as JSON"
    )
    parser.add_argument(
        "--hourly-limit", type=int, default=None, help="Custom hourly quota limit"
    )
    parser.add_argument(
        "--weekly-limit", type=int, default=None, help="Custom weekly quota limit"
    )
    args = parser.parse_args()
    print_usage_cli(
        slot=args.slot,
        as_json=args.json,
        hourly_limit=args.hourly_limit,
        weekly_limit=args.weekly_limit,
    )
