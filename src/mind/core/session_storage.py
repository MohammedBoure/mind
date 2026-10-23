"""Persistent Session Management & Activity Telemetry Engine.

Persists multi-agent orchestration sessions and activity statistics to disk
at `~/.mind/sessions.json`. Tracks session metadata, agent counts, goals,
active status, interaction counts, step counts, and last activity timestamps.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
import json
import logging
import os
from pathlib import Path
from typing import Any

from mind.state.models import SessionInfo

logger = logging.getLogger(__name__)

# Default persistent sessions storage path in the user's home directory
_DEFAULT_DIR = Path.home() / ".mind"
_DEFAULT_SESSIONS_FILE = _DEFAULT_DIR / "sessions.json"
_DEFAULT_CONFIG_FILE = _DEFAULT_DIR / "config.json"


@dataclass
class SessionRecord:
    """Persistent session record with live activity statistics."""

    name: str
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    agent_count: int = 3
    goal: str = ""
    active: bool = True
    total_steps: int = 0
    total_interactions: int = 0
    status: str = "active"
    working_dir: str = ""
    agent_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    global_settings: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize session record to JSON-safe dictionary."""
        return {
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "agent_count": self.agent_count,
            "goal": self.goal,
            "active": self.active,
            "total_steps": self.total_steps,
            "total_interactions": self.total_interactions,
            "status": self.status,
            "working_dir": self.working_dir,
            "agent_configs": self.agent_configs,
            "global_settings": self.global_settings,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionRecord:
        """Instantiate a SessionRecord from serialized dictionary."""
        name = str(data.get("name", "unnamed"))
        created_raw = data.get("created_at")
        last_act_raw = data.get("last_activity")

        created_at = datetime.fromisoformat(created_raw) if created_raw else datetime.now()
        last_activity = datetime.fromisoformat(last_act_raw) if last_act_raw else created_at

        return cls(
            name=name,
            created_at=created_at,
            last_activity=last_activity,
            agent_count=int(data.get("agent_count", 3)),
            goal=str(data.get("goal", "")),
            active=bool(data.get("active", True)),
            total_steps=int(data.get("total_steps", 0)),
            total_interactions=int(data.get("total_interactions", 0)),
            status=str(data.get("status", "active")),
            working_dir=str(data.get("working_dir", "")),
            agent_configs=data.get("agent_configs", {}) or {},
            global_settings=data.get("global_settings", {}) or {},
        )

    def to_session_info(self) -> SessionInfo:
        """Convert to legacy SessionInfo domain model."""
        return SessionInfo(
            name=self.name,
            created_at=self.created_at,
            agent_count=self.agent_count,
            goal=self.goal,
            active=self.active,
        )


def get_default_sessions_path() -> Path:
    """Return default path to persistent sessions file, ensuring parent directory exists."""
    _DEFAULT_DIR.mkdir(parents=True, exist_ok=True)
    return _DEFAULT_SESSIONS_FILE


def _get_initial_seed_sessions() -> list[SessionRecord]:
    """Provide default seed sessions when sessions file does not exist yet."""
    now = datetime.now()
    return [
        SessionRecord(
            name="default",
            created_at=now - timedelta(days=1),
            last_activity=now - timedelta(minutes=45),
            agent_count=2,
            goal="General development workspace",
            active=True,
            total_steps=42,
            total_interactions=8,
            status="active",
        ),
        SessionRecord(
            name="refactor-core",
            created_at=now - timedelta(hours=5),
            last_activity=now - timedelta(hours=1),
            agent_count=4,
            goal="Core engine multiplexing and PTY optimization",
            active=True,
            total_steps=128,
            total_interactions=24,
            status="active",
        ),
        SessionRecord(
            name="aze",
            created_at=now - timedelta(hours=2),
            last_activity=now - timedelta(minutes=15),
            agent_count=3,
            goal="Full integration and verification suite",
            active=True,
            total_steps=19,
            total_interactions=5,
            status="idle",
        ),
    ]


def load_all_sessions(storage_path: Path | None = None) -> list[SessionRecord]:
    """Load all persisted sessions from disk. Initializes default seeds if file missing."""
    file_path = storage_path or get_default_sessions_path()
    if not file_path.exists():
        initial = _get_initial_seed_sessions()
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump([s.to_dict() for s in initial], f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Could not persist initial sessions to {file_path}: {e}")
        return initial

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_list = json.load(f)
        if not isinstance(raw_list, list):
            return _get_initial_seed_sessions()
        loaded = [SessionRecord.from_dict(item) for item in raw_list]
        if not any(s.name == "default" for s in loaded):
            loaded.append(_get_initial_seed_sessions()[0])
        return loaded
    except Exception as e:
        logger.error(f"Error loading sessions from {file_path}: {e}")
        return _get_initial_seed_sessions()


def get_session(name: str, storage_path: Path | None = None) -> SessionRecord | None:
    """Find a specific session by name."""
    sessions = load_all_sessions(storage_path=storage_path)
    for s in sessions:
        if s.name == name:
            return s
    return None


def save_session(
    session: SessionRecord | SessionInfo,
    storage_path: Path | None = None,
) -> SessionRecord:
    """Save or update a session in the persistent storage."""
    file_path = storage_path or get_default_sessions_path()
    sessions = load_all_sessions(storage_path=file_path)

    if isinstance(session, SessionInfo):
        record = SessionRecord(
            name=session.name,
            created_at=session.created_at,
            last_activity=datetime.now(),
            agent_count=session.agent_count,
            goal=session.goal,
            active=session.active,
        )
    else:
        record = session

    # Update existing or append new
    updated = False
    for i, existing in enumerate(sessions):
        if existing.name == record.name:
            sessions[i] = record
            updated = True
            break

    if not updated:
        sessions.insert(0, record)

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump([s.to_dict() for s in sessions], f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to write sessions to {file_path}: {e}")

    return record


def delete_session(name: str, storage_path: Path | None = None) -> bool:
    """Delete a session by name from persistent storage."""
    file_path = storage_path or get_default_sessions_path()
    sessions = load_all_sessions(storage_path=file_path)

    initial_len = len(sessions)
    sessions = [s for s in sessions if s.name != name]

    if len(sessions) == initial_len:
        return False

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump([s.to_dict() for s in sessions], f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Failed to delete session {name} from {file_path}: {e}")
        return False


def record_session_activity(
    name: str,
    steps: int = 1,
    status: str | None = None,
    storage_path: Path | None = None,
) -> SessionRecord | None:
    """Record an activity increment (steps/interaction) and update timestamp for session."""
    session = get_session(name, storage_path=storage_path)
    if not session:
        return None

    session.last_activity = datetime.now()
    session.total_steps += steps
    session.total_interactions += 1
    if status is not None:
        session.status = status

    return save_session(session, storage_path=storage_path)


def get_default_config_path() -> Path:
    """Return default path to global configuration file (~/.mind/config.json)."""
    _DEFAULT_DIR.mkdir(parents=True, exist_ok=True)
    return _DEFAULT_CONFIG_FILE


def load_global_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load global user preferences and configuration from disk."""
    file_path = config_path or get_default_config_path()
    if not file_path.exists():
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"Failed to load global config from {file_path}: {e}")
        return {}


def save_global_config(config: dict[str, Any], config_path: Path | None = None) -> None:
    """Persist global user preferences and configuration to disk."""
    file_path = config_path or get_default_config_path()
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        # Merge with existing config
        existing = load_global_config(config_path=file_path)
        existing.update(config)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save global config to {file_path}: {e}")


def update_global_config(config_path: Path | None = None, **kwargs: Any) -> None:
    """Convenience helper to update specific global configuration keys."""
    save_global_config(kwargs, config_path=config_path)


def update_session_worker_config(
    session_name: str,
    worker_id: str,
    config: dict[str, Any],
    storage_path: Path | None = None,
) -> SessionRecord | None:
    """Persist updated worker/coordinator configuration for a session."""
    session = get_session(session_name, storage_path=storage_path)
    if not session:
        # Create session record if not found
        session = SessionRecord(name=session_name)

    if not isinstance(session.agent_configs, dict):
        session.agent_configs = {}

    session.agent_configs[str(worker_id)] = dict(config)
    session.last_activity = datetime.now()
    return save_session(session, storage_path=storage_path)
