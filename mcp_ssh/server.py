from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

from .audit import AuditLogger
from .config import default_config_path, load_config
from .errors import MCPSSHError
from .models import AppConfig, BlockedResult, ShellType
from .safety import classify_command
from .session_manager import SessionManager


async def _reap_loop(manager: SessionManager) -> None:
    while True:
        await asyncio.sleep(60)
        await manager.reap_idle()


@asynccontextmanager
async def _lifespan(server):
    state = _get_state()
    task = asyncio.create_task(_reap_loop(state.manager))
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await state.manager.close_all()


mcp = FastMCP("mcp-ssh", lifespan=_lifespan)


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
    try:
        conn = await state.manager.get(host_name)
        use_shell = interactive or conn.cfg.shell is ShellType.cli
        if use_shell:
            result = await conn.run_in_shell(command)
        else:
            result = await conn.run_exec(command)
    except MCPSSHError as exc:
        return {"error": str(exc), "type": type(exc).__name__}
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
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "sse":
        auth_token = os.environ.get("MCP_AUTH_TOKEN", "")
        if not auth_token:
            raise SystemExit(
                "ERROR: MCP_AUTH_TOKEN must be set when running in SSE mode. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        # Default to loopback — operator must explicitly set MCP_HOST=0.0.0.0
        # only when a reverse proxy handles auth in front.
        host = os.environ.get("MCP_HOST", "127.0.0.1")
        port = int(os.environ.get("MCP_PORT", "8000"))
        _run_sse_with_auth(host, port, auth_token)
    else:
        mcp.run()


def _run_sse_with_auth(host: str, port: int, auth_token: str) -> None:
    import uvicorn
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import Response

    class BearerAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            import hmac
            authorization = request.headers.get("Authorization", "")
            provided = authorization[7:] if authorization.startswith("Bearer ") else ""
            if not hmac.compare_digest(provided, auth_token):
                return Response("Unauthorized", status_code=401)
            return await call_next(request)

    sse_app = mcp.sse_app()
    app = Starlette(
        routes=sse_app.routes,
        middleware=[Middleware(BearerAuthMiddleware)],
    )
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
