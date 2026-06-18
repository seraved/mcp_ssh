from __future__ import annotations

import os
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

from .audit import AuditLogger
from .config import default_config_path, load_config
from .models import AppConfig, BlockedResult, ShellType
from .safety import classify_command
from .session_manager import SessionManager

mcp = FastMCP("mcp-ssh")


@dataclass
class AppState:
    config: AppConfig
    manager: object
    audit: AuditLogger


_state: AppState | None = None


def set_state(state: AppState) -> None:
    global _state
    _state = state


def _get_state() -> AppState:
    if _state is None:
        raise RuntimeError("Server state not initialized")
    return _state


async def _execute(host_name, command, tool_name, confirm_dangerous, interactive):
    state = _get_state()
    decision = classify_command(command, state.config.settings.deny_patterns)
    if decision.dangerous and not confirm_dangerous:
        state.audit.log(host=host_name, tool=tool_name, command=command,
                        decision="blocked_pending_confirm")
        return BlockedResult(
            reason=f"Command matches a dangerous pattern: '{decision.matched_pattern}'",
            matched_pattern=decision.matched_pattern,
            hint="Re-call with confirm_dangerous=true if this is intentional.",
        ).model_dump()

    state.audit.log(host=host_name, tool=tool_name, command=command,
                    decision="allowed")
    conn = await state.manager.get(host_name)
    use_shell = interactive or conn.cfg.shell is ShellType.cli
    if use_shell:
        result = await conn.run_in_shell(command)
    else:
        result = await conn.run_exec(command)
    state.audit.log(host=host_name, tool=tool_name, command=command,
                    decision="executed", exit_code=result.exit_code,
                    timed_out=result.timed_out)
    return result.model_dump()


@mcp.tool()
async def ssh_list_hosts() -> list[dict]:
    """List configured SSH hosts (no secrets)."""
    state = _get_state()
    return [
        {"name": name, "host": h.host, "user": h.user, "shell": h.shell.value}
        for name, h in state.config.hosts.items()
    ]


@mcp.tool()
async def ssh_connect(host_name: str) -> dict:
    """Open or reuse a persistent SSH session for a host."""
    state = _get_state()
    await state.manager.get(host_name)
    return {"status": "connected", "host": host_name}


@mcp.tool()
async def ssh_run(host_name: str, command: str, confirm_dangerous: bool = False) -> dict:
    """Run a single stateless command (exec for posix hosts)."""
    return await _execute(host_name, command, "ssh_run", confirm_dangerous,
                          interactive=False)


@mcp.tool()
async def ssh_shell(host_name: str, command: str, confirm_dangerous: bool = False) -> dict:
    """Run a command in the persistent interactive shell (keeps state)."""
    return await _execute(host_name, command, "ssh_shell", confirm_dangerous,
                          interactive=True)


@mcp.tool()
async def ssh_list_sessions() -> list[dict]:
    """List active sessions and their idle time."""
    return _get_state().manager.list_sessions()


@mcp.tool()
async def ssh_disconnect(host_name: str) -> dict:
    """Close a session."""
    closed = await _get_state().manager.disconnect(host_name)
    return {"status": "disconnected" if closed else "not_connected", "host": host_name}


def main() -> None:
    config = load_config(default_config_path(), os.environ)
    manager = SessionManager(config, os.environ)
    audit = AuditLogger(config.settings.audit_log)
    set_state(AppState(config=config, manager=manager, audit=audit))
    mcp.run()


if __name__ == "__main__":
    main()
