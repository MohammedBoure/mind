"""CLI entrypoint for the mind TUI and embedded MCP server."""

from __future__ import annotations

import shutil
import subprocess
import sys

import click


@click.group(invoke_without_command=True)
@click.option(
    "-u",
    "--usage",
    is_flag=True,
    help="Display accounts quota & usage monitor table for agy worker slots.",
)
@click.pass_context
def main(ctx: click.Context, usage: bool) -> None:
    """mind — AI Multi-Agent Orchestration TUI.

    Launch the TUI to manage multi-agent sessions.
    Running without arguments opens the session picker.
    """
    # Auto-provision MCP configuration for orchestrator instances
    try:
        from mind.mcp.runner import provision_mcp_config
        provision_mcp_config()
    except Exception:
        pass

    if usage:
        from mind.core.usage_monitor import print_usage_cli

        print_usage_cli()
        return

    if ctx.invoked_subcommand is None:
        from mind.app import MindApp

        app = MindApp()
        app.run()


@main.command("usage")
@click.option(
    "--slot",
    "-s",
    default=None,
    help="Specific agy worker slot to inspect (e.g. agy1).",
)
@click.option(
    "--json",
    "-j",
    "as_json",
    is_flag=True,
    help="Output usage statistics in JSON format.",
)
@click.option(
    "--hourly-limit",
    type=int,
    default=None,
    help="Custom hourly quota limit.",
)
@click.option(
    "--weekly-limit",
    type=int,
    default=None,
    help="Custom weekly quota limit.",
)
def usage_cmd(
    slot: str | None,
    as_json: bool,
    hourly_limit: int | None,
    weekly_limit: int | None,
) -> None:
    """Display accounts quota & usage monitor table for agy worker slots."""
    from mind.core.usage_monitor import print_usage_cli

    print_usage_cli(
        slot=slot,
        as_json=as_json,
        hourly_limit=hourly_limit,
        weekly_limit=weekly_limit,
    )


@main.command()
@click.argument("session_name")
def new(session_name: str) -> None:
    """Create and enter a new session workspace.

    Directly initializes the TUI workspace under SESSION_NAME.
    """
    from mind.app import MindApp

    app = MindApp(initial_session=session_name)
    app.run()


@main.command()
def mcp() -> None:
    """Run the embedded MCP server over standard input/output.

    Useful when registering with agy or other stdio-based MCP clients:
    agy.exe mcp add mind-mcp mind mcp
    """
    from mind.mcp.runner import run_stdio_mcp_server

    run_stdio_mcp_server()


@main.command("register-mcp")
@click.option(
    "--transport",
    "-t",
    type=click.Choice(["stdio", "sse"]),
    default="stdio",
    help="MCP transport to register with agy (default: stdio).",
)
@click.option(
    "--port",
    "-p",
    default=8765,
    help="Port of the background server (default: 8765).",
)
def register_mcp(transport: str, port: int) -> None:
    """Register the mind-mcp server with agy automatically.

    Enables the primary agent running agy to discover and call
    mind-mcp tools (inspect screens, inject interrupts, send input).
    """
    from mind.mcp.runner import provision_mcp_config, resolve_python_path

    # 1. Directly provision mcp_config.json files across orchestrator instances
    try:
        provisioned = provision_mcp_config(port=port)
        if provisioned:
            click.secho(f"Provisioned mind-mcp in {len(provisioned)} instance configuration file(s).", fg="green")
    except Exception as exc:
        click.secho(f"Warning: Auto-provisioning mcp_config.json encountered error: {exc}", fg="yellow")

    agy_path = shutil.which("agy") or shutil.which("agy.exe")
    if not agy_path and sys.platform == "win32":
        import os
        local_agy = os.path.expandvars(r"%LOCALAPPDATA%\agy\bin\agy.exe")
        if os.path.exists(local_agy):
            agy_path = local_agy

    if not agy_path:
        click.echo("Error: 'agy' CLI executable could not be found on PATH.", err=True)
        sys.exit(1)

    if transport == "sse":
        target = f"http://127.0.0.1:{port}/sse"
        cmd = [agy_path, "mcp", "add", "mind-mcp", target]
    else:
        executable = resolve_python_path()
        cmd = [agy_path, "mcp", "add", "mind-mcp", executable, "-m", "mind.cli.main", "mcp"]

    click.echo(f"Registering mind-mcp with agy: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        click.secho("Successfully registered mind-mcp with agy!", fg="green")
        if result.stdout.strip():
            click.echo(result.stdout.strip())
    else:
        click.secho(f"Registration failed (exit code {result.returncode}):", fg="red")
        click.echo(result.stderr or result.stdout)


@main.command("doctor")
@click.option(
    "--json",
    "-j",
    "as_json",
    is_flag=True,
    help="Output diagnostics in structured JSON format.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Display detailed error logs and inspection traces.",
)
def doctor_cmd(as_json: bool, verbose: bool) -> None:
    """Inspect system compatibility, PTY engine, account tokens, and MCP health."""
    from mind.cli.doctor import print_doctor_cli

    exit_code = print_doctor_cli(as_json=as_json, verbose=verbose)
    if exit_code != 0:
        sys.exit(exit_code)


@main.command("sessions")
@click.option(
    "--clean",
    "-c",
    is_flag=True,
    help="Clean up stale or archived temporary sessions.",
)
@click.option(
    "--clean-all",
    is_flag=True,
    help="Clean up all non-default sessions.",
)
@click.option(
    "--days",
    type=int,
    default=7,
    help="Inactivity threshold in days for cleanup (default: 7).",
)
@click.option(
    "--delete",
    "-d",
    default=None,
    help="Delete a specific session by name.",
)
@click.option(
    "--new",
    "-n",
    default=None,
    help="Create a new persistent session with specified name.",
)
@click.option(
    "--agents",
    "-a",
    type=int,
    default=3,
    help="Number of worker agents for the new session (default: 3).",
)
@click.option(
    "--goal",
    "-g",
    default="",
    help="Optional session goal description.",
)
@click.option(
    "--json",
    "-j",
    "as_json",
    is_flag=True,
    help="Output session data in structured JSON format.",
)
def sessions_cmd(
    clean: bool,
    clean_all: bool,
    days: int,
    delete: str | None,
    new: str | None,
    agents: int,
    goal: str,
    as_json: bool,
) -> None:
    """Manage and clean up temporary multi-agent orchestration sessions."""
    from mind.cli.sessions import (
        clean_sessions_cli,
        create_session_cli,
        delete_session_cli,
        list_sessions_cli,
    )

    if delete:
        delete_session_cli(delete)
        return

    if new:
        create_session_cli(name=new, agent_count=agents, goal=goal)
        return

    if clean or clean_all:
        clean_sessions_cli(older_than_days=days, clean_all=clean_all, as_json=as_json)
        return

    list_sessions_cli(as_json=as_json)


if __name__ == "__main__":
    main()
