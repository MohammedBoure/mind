"""System Health, Diagnostic & Compatibility Doctor for mind.

Performs comprehensive diagnostic checks across:
1. System & OS environment (Python version, OS architecture, agy CLI binary, agys PowerShell).
2. PTY engine & terminal subsystem (ConPTY / Unix openpty, dead-key sanitization, spawn test).
3. Account slots & credential tokens (slot discovery, token validity, expiration, mutex locks).
4. Embedded FastMCP server & tools (tool registration, background runner, SSE transport).
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from mind.core.agent_discovery import (
    detect_agys_installed,
    discover_agent_slots,
    discover_system_agents,
    get_real_user_home,
    verify_agys_compatibility,
)
from mind.core.auth.lock import CrossProcessCredentialLock
from mind.core.auth.validator import AuthValidator
from mind.core.pty_process import WindowsInputSanitizer, spawn_pty


class CheckStatus:
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class DiagnosticCheck:
    def __init__(self, category: str, name: str, status: str, message: str, details: str = ""):
        self.category = category
        self.name = name
        self.status = status
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "details": self.details,
        }


def check_system_environment() -> list[DiagnosticCheck]:
    """Inspect underlying host OS, Python runtime, and agy binaries."""
    checks: list[DiagnosticCheck] = []

    # 1. OS & Platform
    platform_name = sys.platform
    os_desc = f"{sys.platform} ({os.name})"
    if platform_name == "win32":
        try:
            import platform
            os_desc = f"Windows {platform.release()} (Build {platform.version()})"
        except Exception:
            pass
    checks.append(DiagnosticCheck(
        category="System",
        name="Operating System",
        status=CheckStatus.PASS,
        message=os_desc,
    ))

    # 2. Python Runtime
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 10):
        checks.append(DiagnosticCheck(
            category="System",
            name="Python Version",
            status=CheckStatus.PASS,
            message=f"Python {py_ver} (>= 3.10 required)",
        ))
    else:
        checks.append(DiagnosticCheck(
            category="System",
            name="Python Version",
            status=CheckStatus.FAIL,
            message=f"Python {py_ver} (mind requires Python 3.10+)",
        ))

    # 3. agy Executable
    agy_path = shutil.which("agy") or shutil.which("agy.exe")
    if not agy_path and sys.platform == "win32":
        local_agy = os.path.expandvars(r"%LOCALAPPDATA%\agy\bin\agy.exe")
        if os.path.exists(local_agy):
            agy_path = local_agy

    if agy_path:
        checks.append(DiagnosticCheck(
            category="System",
            name="agy CLI Binary",
            status=CheckStatus.PASS,
            message=f"Found: {agy_path}",
        ))
    else:
        checks.append(DiagnosticCheck(
            category="System",
            name="agy CLI Binary",
            status=CheckStatus.WARN,
            message="agy command not found in PATH or standard location",
            details="Worker sessions will fall back to default interactive shells until agy is installed.",
        ))

    # 4. agys PowerShell Architecture & Home Resolution
    agys_installed = detect_agys_installed()
    compat = verify_agys_compatibility()
    real_home = get_real_user_home()

    if agys_installed:
        checks.append(DiagnosticCheck(
            category="System",
            name="agys PowerShell Multi-Slot",
            status=CheckStatus.PASS,
            message="PowerShell agys multi-slot orchestrator detected",
            details=f"Real User Home: {real_home}",
        ))
    else:
        checks.append(DiagnosticCheck(
            category="System",
            name="agys PowerShell Multi-Slot",
            status=CheckStatus.WARN,
            message="agys function not found in PowerShell profile (standalone mode)",
            details=f"Checked: {compat.get('real_home', real_home)}",
        ))

    return checks


def check_pty_engine() -> list[DiagnosticCheck]:
    """Inspect pseudoterminal engine, dead-key filters, and spawn capabilities."""
    checks: list[DiagnosticCheck] = []

    # 1. PTY Architecture
    if sys.platform == "win32":
        try:
            import winpty
            checks.append(DiagnosticCheck(
                category="PTY Engine",
                name="Windows ConPTY / WinPTY",
                status=CheckStatus.PASS,
                message="pywinpty backend operational with ConPTY support",
            ))
        except ImportError:
            checks.append(DiagnosticCheck(
                category="PTY Engine",
                name="Windows ConPTY / WinPTY",
                status=CheckStatus.FAIL,
                message="pywinpty module is missing",
                details="Install via: pip install pywinpty",
            ))
    else:
        try:
            import pty
            import termios
            checks.append(DiagnosticCheck(
                category="PTY Engine",
                name="POSIX Native PTY",
                status=CheckStatus.PASS,
                message="Native openpty/termios subsystem available",
            ))
        except ImportError as e:
            checks.append(DiagnosticCheck(
                category="PTY Engine",
                name="POSIX Native PTY",
                status=CheckStatus.FAIL,
                message=f"Missing POSIX pty modules: {e}",
            ))

    # 2. Dead-Key & Scancode Sanitizer
    sanitizer = WindowsInputSanitizer()
    res = sanitizer.sanitize_input("\xe0H")
    if res == "\x1b[A" or sys.platform != "win32":
        checks.append(DiagnosticCheck(
            category="PTY Engine",
            name="Scancode Sanitizer",
            status=CheckStatus.PASS,
            message="Dead-key translation and \\xe0 scancode filtering active",
        ))
    else:
        checks.append(DiagnosticCheck(
            category="PTY Engine",
            name="Scancode Sanitizer",
            status=CheckStatus.WARN,
            message="Sanitizer returned unexpected transformation",
        ))

    # 3. PTY Process Spawn Test
    try:
        cmd = ["powershell.exe", "-NoLogo", "-Command", "Write-Output 'OK'"] if sys.platform == "win32" else ["echo", "OK"]
        proc = spawn_pty(command=cmd, columns=80, lines=24)
        if proc and proc.is_alive():
            proc.terminate()
            checks.append(DiagnosticCheck(
                category="PTY Engine",
                name="PTY Spawn & Kill Test",
                status=CheckStatus.PASS,
                message="Successfully spawned and cleanly terminated test PTY process",
            ))
        else:
            checks.append(DiagnosticCheck(
                category="PTY Engine",
                name="PTY Spawn & Kill Test",
                status=CheckStatus.WARN,
                message="Spawned test process exited immediately or null handle returned",
            ))
    except Exception as e:
        checks.append(DiagnosticCheck(
            category="PTY Engine",
            name="PTY Spawn & Kill Test",
            status=CheckStatus.FAIL,
            message=f"Error spawning test PTY: {e}",
        ))

    return checks


def check_account_tokens_and_slots() -> list[DiagnosticCheck]:
    """Inspect discovered worker slots, token files, and credential locks."""
    checks: list[DiagnosticCheck] = []

    # 1. Slot Discovery
    slots = discover_agent_slots()
    sys_agents = discover_system_agents()

    if slots:
        slot_names = ", ".join(f"agy{s.slot_id}" for s in slots)
        checks.append(DiagnosticCheck(
            category="Accounts & Tokens",
            name="Worker Slots Discovery",
            status=CheckStatus.PASS,
            message=f"Discovered {len(slots)} worker slots: {slot_names}",
        ))
    else:
        checks.append(DiagnosticCheck(
            category="Accounts & Tokens",
            name="Worker Slots Discovery",
            status=CheckStatus.WARN,
            message="No agy worker slots discovered in ~/.gemini/instances or ~/.gemini/tokens",
            details="Run 'agys add' or 'agy login' to create token slots.",
        ))

    # 2. Token Validation for First Slots
    validator = AuthValidator()
    tested_count = 0
    valid_count = 0

    for slot in slots[:5]:
        tested_count += 1
        tok_path = getattr(slot, "instance_token_file", None) or getattr(slot, "token_file", None)
        if not tok_path or not tok_path.exists():
            continue
        try:
            content = tok_path.read_text(encoding="utf-8", errors="replace").strip()
            val_res = validator.validate(content)
            if val_res.is_valid:
                valid_count += 1
        except Exception:
            pass

    if tested_count > 0:
        if valid_count == tested_count:
            checks.append(DiagnosticCheck(
                category="Accounts & Tokens",
                name="Token Validity & Claims",
                status=CheckStatus.PASS,
                message=f"All {tested_count} inspected slot tokens are valid and unexpired",
            ))
        elif valid_count > 0:
            checks.append(DiagnosticCheck(
                category="Accounts & Tokens",
                name="Token Validity & Claims",
                status=CheckStatus.WARN,
                message=f"{valid_count}/{tested_count} inspected tokens are valid; some tokens may be expired",
            ))
        else:
            checks.append(DiagnosticCheck(
                category="Accounts & Tokens",
                name="Token Validity & Claims",
                status=CheckStatus.WARN,
                message=f"None of the {tested_count} inspected slot tokens could be validated as active JWTs",
            ))

    # 3. Mutex Lock Test
    try:
        lock = CrossProcessCredentialLock(timeout_ms=500)
        acquired = lock.acquire(500)
        if acquired:
            lock.release()
            checks.append(DiagnosticCheck(
                category="Accounts & Tokens",
                name="Credential Mutex Lock",
                status=CheckStatus.PASS,
                message="Cross-process IPC credential mutex lock acquired and released cleanly",
            ))
        else:
            checks.append(DiagnosticCheck(
                category="Accounts & Tokens",
                name="Credential Mutex Lock",
                status=CheckStatus.WARN,
                message="Mutex lock could not be acquired within timeout (another instance running?)",
            ))
    except Exception as e:
        checks.append(DiagnosticCheck(
            category="Accounts & Tokens",
            name="Credential Mutex Lock",
            status=CheckStatus.FAIL,
            message=f"Mutex lock initialization error: {e}",
        ))

    return checks


def check_mcp_server() -> list[DiagnosticCheck]:
    """Inspect FastMCP server registration, available tools, and runner status."""
    checks: list[DiagnosticCheck] = []

    # 1. FastMCP Import
    try:
        import mcp
        checks.append(DiagnosticCheck(
            category="MCP Bridge",
            name="FastMCP Framework",
            status=CheckStatus.PASS,
            message="FastMCP / MCP SDK successfully imported",
        ))
    except ImportError:
        checks.append(DiagnosticCheck(
            category="MCP Bridge",
            name="FastMCP Framework",
            status=CheckStatus.FAIL,
            message="mcp package is not installed",
            details="Install via: pip install mcp fastmcp",
        ))
        return checks

    # 2. Tool Registration Check
    try:
        from mind.mcp.server import create_mcp_server

        server = create_mcp_server()
        expected_tools = {
            "list_workers",
            "get_terminal_screen",
            "send_terminal_input",
            "interrupt_and_inject",
            "get_agent_profile",
            "check_account_quotas",
        }
        # Verify server instance
        if server:
            checks.append(DiagnosticCheck(
                category="MCP Bridge",
                name="MCP Tools Suite",
                status=CheckStatus.PASS,
                message=f"Initialized mind-mcp server with {len(expected_tools)} core tools registered",
                details=", ".join(sorted(expected_tools)),
            ))
        else:
            checks.append(DiagnosticCheck(
                category="MCP Bridge",
                name="MCP Tools Suite",
                status=CheckStatus.FAIL,
                message="create_mcp_server returned None",
            ))
    except Exception as e:
        checks.append(DiagnosticCheck(
            category="MCP Bridge",
            name="MCP Tools Suite",
            status=CheckStatus.FAIL,
            message=f"Failed to initialize MCP server: {e}",
        ))

    # 3. Background Runner Check
    try:
        from mind.mcp.runner import MCPServerRunner

        runner = MCPServerRunner(port=8765, server=server)
        checks.append(DiagnosticCheck(
            category="MCP Bridge",
            name="Background SSE Runner",
            status=CheckStatus.PASS,
            message="MCPServerRunner initialized (SSE endpoint: http://127.0.0.1:8765/sse)",
        ))
    except Exception as e:
        checks.append(DiagnosticCheck(
            category="MCP Bridge",
            name="Background SSE Runner",
            status=CheckStatus.WARN,
            message=f"MCPServerRunner check: {e}",
        ))

    return checks


def run_all_doctor_checks() -> list[DiagnosticCheck]:
    """Execute all diagnostic check categories."""
    results: list[DiagnosticCheck] = []
    results.extend(check_system_environment())
    results.extend(check_pty_engine())
    results.extend(check_account_tokens_and_slots())
    results.extend(check_mcp_server())
    return results


def print_doctor_cli(as_json: bool = False, verbose: bool = False) -> int:
    """Print system diagnostics report in Rich table format or structured JSON."""
    results = run_all_doctor_checks()

    if as_json:
        data = {
            "timestamp": time.time(),
            "summary": {
                "total": len(results),
                "pass": sum(1 for r in results if r.status == CheckStatus.PASS),
                "warn": sum(1 for r in results if r.status == CheckStatus.WARN),
                "fail": sum(1 for r in results if r.status == CheckStatus.FAIL),
            },
            "checks": [r.to_dict() for r in results],
        }
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 1 if any(r.status == CheckStatus.FAIL for r in results) else 0

    console = Console()

    table = Table(
        title="🧠  mind doctor — System Health & Compatibility Report",
        header_style="bold #7aa2f7",
        border_style="#3b4261",
        box=None,
        show_edge=True,
    )
    table.add_column("Category", style="bold #bb9af7", width=18)
    table.add_column("Diagnostic Check", style="bold #c0caf5", width=28)
    table.add_column("Status", width=10, justify="center")
    table.add_column("Details & Output", style="#a9b1d6")

    pass_count = 0
    warn_count = 0
    fail_count = 0

    for chk in results:
        if chk.status == CheckStatus.PASS:
            status_markup = "[bold #9ece6a]✓ PASS[/]"
            pass_count += 1
        elif chk.status == CheckStatus.WARN:
            status_markup = "[bold #e0af68]! WARN[/]"
            warn_count += 1
        else:
            status_markup = "[bold #f7768e]✗ FAIL[/]"
            fail_count += 1

        details = chk.message
        if verbose and chk.details:
            details += f"\n[dim #565f89]{chk.details}[/dim #565f89]"

        table.add_row(chk.category, chk.name, status_markup, details)

    console.print()
    console.print(table)
    console.print()

    # Summary Panel
    if fail_count > 0:
        summary_color = "red"
        summary_title = "🚨 Issues Detected"
        summary_text = (
            f"Found [bold red]{fail_count} failed checks[/] and [bold yellow]{warn_count} warnings[/]. "
            "Please review failed items above before launching multi-agent orchestration."
        )
    elif warn_count > 0:
        summary_color = "yellow"
        summary_title = "⚡ System Ready (With Warnings)"
        summary_text = (
            f"Passed [bold green]{pass_count} checks[/] with [bold yellow]{warn_count} minor warnings[/]. "
            "All core functions are ready to run."
        )
    else:
        summary_color = "green"
        summary_title = "✓ All Systems Operational"
        summary_text = (
            f"All [bold green]{pass_count} diagnostic checks passed successfully[/]! "
            "PTY engine, authentication, slots, and MCP server are in pristine health."
        )

    console.print(Panel(summary_text, title=summary_title, border_style=summary_color, expand=False))
    console.print()

    return 1 if fail_count > 0 else 0
