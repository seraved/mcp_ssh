from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

from .audit import AuditLogger
from .config import default_config_path, load_config
from .errors import MCPSSHError
from .models import AppConfig, BlockedResult, ShellType
from .safety import evaluate_policy
from .session_manager import SessionManager


async def _reap_loop(manager: SessionManager) -> None:
    while True:
        await asyncio.sleep(60)
        await manager.reap_idle()


async def _config_reload_loop(path: str, interval: int = 5) -> None:
    mtime = os.path.getmtime(path)
    while True:
        await asyncio.sleep(interval)
        try:
            new_mtime = os.path.getmtime(path)
            if new_mtime == mtime:
                continue
            new_config = load_config(path)
            state = _get_state()
            old_hosts = set(state.config.hosts)
            new_hosts = set(new_config.hosts)
            state.config = new_config
            state.manager._config = new_config
            mtime = new_mtime
            parts = []
            added = new_hosts - old_hosts
            removed = old_hosts - new_hosts
            if added:
                parts.append(f"+{','.join(sorted(added))}")
            if removed:
                parts.append(f"-{','.join(sorted(removed))}")
            delta = " ".join(parts) or "no host changes"
            print(f"[mcp-ssh] config reloaded: {delta}", flush=True, file=sys.stderr)
        except Exception as exc:
            print(f"[mcp-ssh] config reload failed: {exc}", flush=True, file=sys.stderr)


@asynccontextmanager
async def _lifespan(server):
    state = _get_state()
    reap_task = asyncio.create_task(_reap_loop(state.manager))
    reload_task = asyncio.create_task(
        _config_reload_loop(state.config_path, state.reload_interval)
    )
    try:
        yield
    finally:
        reap_task.cancel()
        reload_task.cancel()
        await asyncio.gather(reap_task, reload_task, return_exceptions=True)
        await state.manager.close_all()


mcp = FastMCP("mcp-ssh", lifespan=_lifespan, host=os.getenv("MCP_HOST", "127.0.0.1"))


@dataclass
class AppState:
    config: AppConfig
    manager: object
    audit: AuditLogger
    config_path: str
    reload_interval: int


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
    host_cfg = state.config.hosts.get(host_name)
    policy = evaluate_policy(
        host_name, host_cfg, tool_name, command, state.config.settings.deny_patterns
    )
    if not policy.allowed:
        if policy.bypassable and confirm_dangerous:
            pass  # unrestricted mode — caller explicitly confirmed
        else:
            state.audit.log(
                host=host_name, tool=tool_name, command=command,
                decision="blocked", reason=policy.reason,
            )
            return BlockedResult(
                reason=policy.reason or "Blocked by security policy.",
                matched_pattern=policy.matched_pattern,
                hint="Use confirm_dangerous=true in unrestricted mode, or change the host mode in config.",
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
    config_path = default_config_path()
    config = load_config(config_path, os.environ)
    if audit_log_env := os.environ.get("MCP_AUDIT_LOG"):
        config.settings.audit_log = audit_log_env
    reload_interval = int(os.environ.get("MCP_RELOAD_INTERVAL", "5"))
    manager = SessionManager(config, os.environ)
    audit = AuditLogger(config.settings.audit_log)
    set_state(AppState(
        config=config,
        manager=manager,
        audit=audit,
        config_path=config_path,
        reload_interval=reload_interval,
    ))
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport in ("sse", "http"):
        auth_token = os.environ.get("MCP_AUTH_TOKEN", "")
        if not auth_token:
            raise SystemExit(
                "ERROR: MCP_AUTH_TOKEN must be set when running in SSE/HTTP mode. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        # Default to loopback — operator must explicitly set MCP_HOST=0.0.0.0
        # only when a reverse proxy handles auth in front.
        host = os.environ.get("MCP_HOST", "127.0.0.1")
        port = int(os.environ.get("MCP_PORT", "8000"))
        if transport == "http":
            _run_http_with_auth(host, port, auth_token)
        else:
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


def _run_http_with_auth(host: str, port: int, auth_token: str) -> None:
    import uvicorn
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

    http_app = mcp.streamable_http_app()
    http_app.add_middleware(BearerAuthMiddleware)
    uvicorn.run(http_app, host=host, port=port)


if __name__ == "__main__":
    main()
