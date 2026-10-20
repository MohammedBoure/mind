"""CLI entrypoint for the mind TUI and embedded MCP server."""

from __future__ import annotations

import shutil
import subprocess
import sys

import click


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx: click.Context) -> None:
    """mind — AI Multi-Agent Orchestration TUI.

    Launch the TUI to manage multi-agent sessions.
    Running without arguments opens the session picker.
    """
    if ctx.invoked_subcommand is None:
        from micro.app import MicroApp

        app = MicroApp()
        app.run()


@main.command()
@click.argument("session_name")
def new(session_name: str) -> None:
    """Create and enter a new session workspace.

    Directly initializes the TUI workspace under SESSION_NAME.
    """
    from micro.app import MicroApp

    app = MicroApp(initial_session=session_name)
    app.run()


@main.command()
def mcp() -> None:
    """Run the embedded MCP server over standard input/output.

    Useful when registering with agy or other stdio-based MCP clients:
    agy.exe mcp add mind-mcp micro mcp
    """
    from micro.mcp.runner import run_stdio_mcp_server

    run_stdio_mcp_server()


@main.command("register-mcp")
@click.option(
    "--transport",
    "-t",
    type=click.Choice(["sse", "stdio"]),
    default="sse",
    help="MCP transport to register with agy (default: sse).",
)
@click.option(
    "--port",
    "-p",
    default=8765,
    help="Port of the background SSE server (default: 8765).",
)
def register_mcp(transport: str, port: int) -> None:
    """Register the mind-mcp server with agy automatically.

    Enables the primary agent running agy to discover and call
    mind-mcp tools (inspect screens, inject interrupts, send input).
    """
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
        executable = sys.executable
        cmd = [agy_path, "mcp", "add", "mind-mcp", executable, "-m", "micro.cli.main", "mcp"]

    click.echo(f"Registering mind-mcp with agy: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        click.secho("✓ Successfully registered mind-mcp with agy!", fg="green")
        if result.stdout.strip():
            click.echo(result.stdout.strip())
    else:
        click.secho(f"Registration failed (exit code {result.returncode}):", fg="red")
        click.echo(result.stderr or result.stdout)


if __name__ == "__main__":
    main()
