"""Mock data provider for the micro TUI.

All data here is placeholder content. Replace with real MCP server
connections and agent event streams when wiring up the backend.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import random

from micro.state.models import (
    AgentInfo,
    AgentRole,
    AgentStatus,
    InterAgentMessage,
    LogEntry,
    MessagePriority,
    SessionInfo,
)

# ── Mock Sessions ──────────────────────────────────────────────────
MOCK_SESSIONS: list[SessionInfo] = [
    SessionInfo(
        name="aze",
        created_at=datetime.now() - timedelta(hours=2),
        agent_count=3,
        goal="Refactor authentication module",
        active=True,
    ),
    SessionInfo(
        name="default",
        created_at=datetime.now() - timedelta(days=1),
        agent_count=2,
        goal="General development workspace",
        active=True,
    ),
    SessionInfo(
        name="refactor-core",
        created_at=datetime.now() - timedelta(hours=5),
        agent_count=4,
        goal="Core engine refactoring with test coverage",
        active=True,
    ),
]


def get_mock_agents(count: int = 3) -> list[AgentInfo]:
    """Generate a list of mock agents for a session."""
    agents = [
        AgentInfo(
            id=0,
            name="Primary Agent",
            role=AgentRole.PRIMARY,
            status=AgentStatus.THINKING,
            model="gpt-4o",
            task="Coordinating refactor workflow",
        ),
    ]
    worker_tasks = [
        "Analyzing module dependencies",
        "Running test suite",
        "Generating documentation",
        "Code review pass",
        "Linting & formatting",
    ]
    worker_statuses = [
        AgentStatus.EXECUTING,
        AgentStatus.IDLE,
        AgentStatus.WAITING,
        AgentStatus.THINKING,
    ]
    for i in range(1, count):
        agents.append(
            AgentInfo(
                id=i,
                name=f"Worker-{i}",
                role=AgentRole.WORKER,
                status=random.choice(worker_statuses),
                model="gpt-4o-mini",
                task=worker_tasks[i % len(worker_tasks)],
            )
        )
    return agents


# ── Mock Log Streams ───────────────────────────────────────────────
_PRIMARY_LOG_LINES: list[tuple[str, str]] = [
    ("thought", "Analyzing project structure for refactoring opportunities..."),
    ("thought", "Identified 3 modules with high coupling: auth, db, api."),
    ("tool_call", "→ read_file('src/auth/handler.py')"),
    ("result", "✓ File loaded (247 lines). Scanning for patterns..."),
    ("thought", "The AuthHandler class violates SRP. Splitting into AuthValidator and TokenManager."),
    ("tool_call", "→ search_codebase('import AuthHandler')"),
    ("result", "✓ Found 12 references across 8 files."),
    ("thought", "Delegating sub-tasks to Worker-1 (test updates) and Worker-2 (doc generation)."),
    ("info", "⚡ Dispatched task to Worker-1: Update test fixtures for new auth split."),
    ("info", "⚡ Dispatched task to Worker-2: Regenerate API docs for auth module."),
    ("thought", "Monitoring worker progress. Estimated completion: 4 min."),
    ("tool_call", "→ write_file('src/auth/validator.py', content=...)"),
    ("result", "✓ Created src/auth/validator.py (89 lines)"),
]

_WORKER_LOG_LINES: list[tuple[str, str]] = [
    ("info", "Received task assignment from Primary Agent."),
    ("thought", "Parsing task requirements..."),
    ("tool_call", "→ list_files('tests/auth/')"),
    ("result", "✓ Found 5 test files."),
    ("tool_call", "→ read_file('tests/auth/test_handler.py')"),
    ("result", "✓ File loaded (183 lines)."),
    ("thought", "Need to split test_handler into test_validator and test_token_manager."),
    ("tool_call", "→ write_file('tests/auth/test_validator.py', content=...)"),
    ("result", "✓ Created tests/auth/test_validator.py (94 lines)"),
    ("info", "Running pytest on new test files..."),
    ("result", "✓ 12 tests passed, 0 failed."),
    ("info", "Task complete. Reporting back to Primary Agent."),
]


def get_mock_log_stream(agent_id: int) -> list[LogEntry]:
    """Get a mock log stream for the given agent."""
    base_time = datetime.now() - timedelta(minutes=5)
    lines = _PRIMARY_LOG_LINES if agent_id == 0 else _WORKER_LOG_LINES
    entries: list[LogEntry] = []
    for i, (entry_type, content) in enumerate(lines):
        entries.append(
            LogEntry(
                timestamp=base_time + timedelta(seconds=i * 8),
                source=f"Agent-{agent_id}",
                content=content,
                entry_type=entry_type,
            )
        )
    return entries


def get_random_interrupt_message() -> InterAgentMessage:
    """Generate a random inter-agent interrupt message."""
    messages = [
        InterAgentMessage(
            sender="Worker-1",
            receiver="Primary Agent",
            priority=MessagePriority.HIGH,
            directive="Test coverage dropped below 80% after auth split. Requesting guidance.",
        ),
        InterAgentMessage(
            sender="Primary Agent",
            receiver="Worker-2",
            priority=MessagePriority.CRITICAL,
            directive="HALT: Dependency conflict detected in auth module. Pause doc generation.",
        ),
        InterAgentMessage(
            sender="Worker-2",
            receiver="Worker-1",
            priority=MessagePriority.NORMAL,
            directive="Sharing updated API schema for test fixture alignment.",
        ),
        InterAgentMessage(
            sender="Supervisor",
            receiver="Primary Agent",
            priority=MessagePriority.CRITICAL,
            directive="User override: Prioritize security audit before continuing refactor.",
        ),
    ]
    return random.choice(messages)
