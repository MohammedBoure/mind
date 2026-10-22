"""Automated unit and integration test suite for Unified CLI Suite & Doctor (Task #15).

Validates:
1. `mind` main Click entrypoint and help outputs.
2. `mind usage` and `-u` / `--usage` flag rendering quota tables & JSON.
3. `mind doctor` diagnostic system health suite:
   - System environment compatibility (OS, Python, agy executable, agys PowerShell).
   - PTY engine & scancode sanitization.
   - Account slots discovery & mutex lock.
   - Embedded FastMCP server & registered tool suite.
   - Structured JSON output format.
4. `mind sessions` orchestration session manager & cleanup:
   - Listing persisted sessions with activity telemetry.
   - Creating new sessions from CLI (`--new`, `--agents`, `--goal`).
   - Deleting sessions from CLI (`--delete`).
   - Cleaning up stale/old sessions (`--clean`).
   - Structured JSON output format.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import pytest
from click.testing import CliRunner

from mind.cli.doctor import (
    CheckStatus,
    check_account_tokens_and_slots,
    check_mcp_server,
    check_pty_engine,
    check_system_environment,
    print_doctor_cli,
    run_all_doctor_checks,
)
from mind.cli.main import main
from mind.cli.sessions import (
    clean_sessions_cli,
    create_session_cli,
    delete_session_cli,
    list_sessions_cli,
)
from mind.core.session_storage import (
    SessionRecord,
    get_session,
    load_all_sessions,
    save_session,
)
from mind.core.terminal_manager import TerminalManager


@pytest.fixture(autouse=True)
def reset_state():
    TerminalManager.reset()
    yield
    TerminalManager.reset()


# ── 1. Root CLI & Help Tests ──────────────────────────────────────────────────

def test_cli_help() -> None:
    """Click runner invokes 'mind --help' and displays unified commands."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "mind — AI Multi-Agent Orchestration TUI" in result.output
    assert "doctor" in result.output
    assert "usage" in result.output
    assert "sessions" in result.output
    assert "register-mcp" in result.output


def test_cli_usage_flag_and_command() -> None:
    """Verify 'mind -u' and 'mind usage --json' output accounts quota telemetry."""
    runner = CliRunner()

    # Short flag -u
    res_flag = runner.invoke(main, ["-u"])
    assert res_flag.exit_code == 0
    assert "Accounts Quota" in res_flag.output or "Slot" in res_flag.output

    # usage subcommand with JSON output
    res_json = runner.invoke(main, ["usage", "--json"])
    assert res_json.exit_code == 0
    parsed = json.loads(res_json.output)
    assert isinstance(parsed, (dict, list))
    if isinstance(parsed, dict):
        assert "slots" in parsed


# ── 2. Doctor Diagnostics Suite Tests ─────────────────────────────────────────

def test_doctor_diagnostic_check_functions() -> None:
    """Run all individual doctor check categories and verify non-empty results."""
    sys_checks = check_system_environment()
    assert len(sys_checks) >= 3
    assert any(c.name == "Python Version" and c.status == CheckStatus.PASS for c in sys_checks)

    pty_checks = check_pty_engine()
    assert len(pty_checks) >= 2
    assert any("PTY" in c.name for c in pty_checks)

    token_checks = check_account_tokens_and_slots()
    assert len(token_checks) >= 1

    mcp_checks = check_mcp_server()
    assert len(mcp_checks) >= 2
    assert any(c.name == "FastMCP Framework" for c in mcp_checks)


def test_doctor_cli_runner() -> None:
    """Invoke 'mind doctor' via Click runner."""
    runner = CliRunner()
    result = runner.invoke(main, ["doctor"])
    assert result.exit_code in (0, 1)  # 0 if all clean, 1 if warnings/fails
    assert "mind doctor — System Health & Compatibility Report" in result.output
    assert "Operating System" in result.output
    assert "FastMCP Framework" in result.output


def test_doctor_json_output() -> None:
    """Verify 'mind doctor --json' produces parseable JSON with summary counts."""
    runner = CliRunner()
    result = runner.invoke(main, ["doctor", "--json"])
    assert result.exit_code in (0, 1)

    # Filter out potential background log lines to locate JSON
    json_start = result.output.find("{")
    assert json_start != -1
    raw_json = result.output[json_start:]
    data = json.loads(raw_json)

    assert "summary" in data
    assert "total" in data["summary"]
    assert "checks" in data
    assert len(data["checks"]) >= 10


# ── 3. Sessions CLI Suite Tests ───────────────────────────────────────────────

def test_sessions_list_cli() -> None:
    """Verify 'mind sessions' lists active sessions and formatted table."""
    runner = CliRunner()
    result = runner.invoke(main, ["sessions"])
    assert result.exit_code == 0
    assert "mind sessions — Persisted Multi-Agent Orchestration Sessions" in result.output
    assert "default" in result.output


def test_sessions_json_cli() -> None:
    """Verify 'mind sessions --json' produces JSON array of session records."""
    runner = CliRunner()
    result = runner.invoke(main, ["sessions", "--json"])
    assert result.exit_code == 0

    parsed = json.loads(result.output)
    assert isinstance(parsed, list)
    assert len(parsed) >= 1
    assert any(s["name"] == "default" for s in parsed)


def test_sessions_create_and_delete_cli() -> None:
    """Verify creating and deleting a session through CLI arguments."""
    runner = CliRunner()
    test_session_name = "cli-doctor-test-session"

    # Create new session
    res_create = runner.invoke(main, ["sessions", "--new", test_session_name, "--agents", "5", "--goal", "Unit testing"])
    assert res_create.exit_code == 0
    assert f"Session '{test_session_name}' created with 5 agents" in res_create.output

    record = get_session(test_session_name)
    assert record is not None
    assert record.agent_count == 5
    assert record.goal == "Unit testing"

    # Delete session
    res_delete = runner.invoke(main, ["sessions", "--delete", test_session_name])
    assert res_delete.exit_code == 0
    assert f"Session '{test_session_name}' deleted successfully" in res_delete.output

    assert get_session(test_session_name) is None


def test_sessions_clean_cli() -> None:
    """Verify 'mind sessions --clean' triggers cleanup routine."""
    runner = CliRunner()
    result = runner.invoke(main, ["sessions", "--clean", "--days", "30"])
    assert result.exit_code == 0
    assert "cleaned" in result.output.lower() or "no sessions matched" in result.output.lower()
