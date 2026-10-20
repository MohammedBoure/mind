"""CLI entrypoint for the micro TUI."""

from __future__ import annotations

import click


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx: click.Context) -> None:
    """mind · micro — AI Multi-Agent Orchestration TUI.

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


if __name__ == "__main__":
    main()
