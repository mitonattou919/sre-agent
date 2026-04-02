"""Click CLI entry point for sre-agent."""

import sys

import click
from rich.console import Console
from rich.markdown import Markdown

from cli import auth, client

console = Console()

_HELP_TEXT = """\
Available commands:
  /exit, /quit   Exit interactive mode
  /session       Show current session ID
  /help          Show this help\
"""


def _render_reply(reply: str, tool_calls: list[str]) -> None:
    for tool in tool_calls:
        console.print(f"🔧 {tool}", style="dim")
    console.print(Markdown(reply))


def _interactive(session_id: str | None = None) -> None:
    """Run interactive chat mode."""
    # Start or reuse session
    response = client.chat("", session_id) if session_id else None

    # Get initial session_id via a dummy call if not provided
    # (session is created on first real message instead)
    current_session: str | None = session_id

    if current_session:
        console.print(f"Session: {current_session}")
    else:
        console.print("Session: (created on first message)")
    console.print("SRE Agent ready. Type /help for commands.\n")

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nGoodbye.")
            if current_session:
                client.delete_session(current_session)
            break

        if not user_input:
            continue

        # Slash commands
        if user_input.startswith("/"):
            cmd = user_input.lower()
            if cmd in ("/exit", "/quit"):
                console.print("Goodbye.")
                if current_session:
                    client.delete_session(current_session)
                break
            elif cmd == "/help":
                console.print(_HELP_TEXT)
            elif cmd == "/session":
                console.print(f"Session: {current_session or '(none)'}")
            else:
                console.print(f"Unknown command '{user_input}'. Type /help for available commands.")
            continue

        # Send message
        data = client.chat(user_input, current_session)
        current_session = data.get("session_id", current_session)

        if current_session and not session_id:
            # Print session ID on first turn
            console.print(f"Session: {current_session}")
            session_id = current_session  # suppress printing again

        _render_reply(data.get("reply", ""), data.get("tool_calls", []))


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """SRE Agent CLI for Azure environments."""
    if ctx.invoked_subcommand is None:
        _interactive()


@cli.command()
def login() -> None:
    """Authenticate via Device Code Flow."""
    auth.login()


@cli.command()
def chat() -> None:
    """Start interactive chat mode."""
    _interactive()


@cli.command()
@click.option("--resource-group", default=None, help="Filter by resource group name.")
@click.option(
    "--severity",
    default=None,
    type=click.IntRange(0, 4),
    help="Filter by severity (0=Critical, 4=Verbose).",
)
def alerts(resource_group: str | None, severity: int | None) -> None:
    """One-shot: list active alerts."""
    msg_parts = ["Show active alerts"]
    if resource_group:
        msg_parts.append(f"in resource group {resource_group}")
    if severity is not None:
        msg_parts.append(f"with severity {severity}")
    message = " ".join(msg_parts)

    data = client.chat(message)
    _render_reply(data.get("reply", ""), data.get("tool_calls", []))


@cli.command()
@click.option(
    "--period",
    default="7d",
    type=click.Choice(["today", "7d", "30d"]),
    help="Aggregation period (default: 7d).",
)
def cost(period: str) -> None:
    """One-shot: cost summary."""
    data = client.chat(f"Show cost summary for the {period} period")
    _render_reply(data.get("reply", ""), data.get("tool_calls", []))
