import pytest

from mcp_ssh import server
from mcp_ssh.errors import ConnectionFailedError, HostNotFoundError
from mcp_ssh.models import (
    AppConfig, AuthConfig, CommandResult, HostConfig, Settings, ShellType,
)


class FakeConn:
    def __init__(self, shell=ShellType.posix):
        self.cfg = HostConfig(host="x", user="u", shell=shell,
                              auth=AuthConfig(method="key", key_path="k"))
        self.exec_calls = []
        self.shell_calls = []

    async def run_exec(self, command, timeout=None):
        self.exec_calls.append(command)
        return CommandResult(output="exec:" + command, exit_code=0)

    async def run_in_shell(self, command, timeout=None):
        self.shell_calls.append(command)
        return CommandResult(output="shell:" + command, exit_code=0)


class FakeManager:
    def __init__(self, conn):
        self._conn = conn

    async def get(self, host_name):
        return self._conn


def _state(tmp_path, conn):
    cfg = AppConfig(hosts={"h1": conn.cfg}, settings=Settings())
    from mcp_ssh.audit import AuditLogger
    state = server.AppState(
        config=cfg,
        manager=FakeManager(conn),
        audit=AuditLogger(str(tmp_path / "audit.log")),
        config_path="/path/hosts.yaml",
        reload_interval=5,
    )
    server.set_state(state)
    return state


async def test_ssh_run_posix_uses_exec(tmp_path):
    conn = FakeConn(shell=ShellType.posix)
    _state(tmp_path, conn)
    out = await server.ssh_run("h1", "ls")
    assert out["output"] == "exec:ls"
    assert conn.exec_calls == ["ls"]


async def test_dangerous_blocked_without_confirm(tmp_path):
    conn = FakeConn()
    _state(tmp_path, conn)
    out = await server.ssh_run("h1", "reboot")
    assert out["blocked"] is True
    assert conn.exec_calls == []


async def test_dangerous_runs_with_confirm(tmp_path):
    conn = FakeConn()
    _state(tmp_path, conn)
    out = await server.ssh_run("h1", "reboot", confirm_dangerous=True)
    assert out.get("blocked") is None
    assert conn.exec_calls == ["reboot"]


async def test_ssh_shell_uses_shell(tmp_path):
    conn = FakeConn()
    _state(tmp_path, conn)
    out = await server.ssh_shell("h1", "cd /tmp")
    assert out["output"] == "shell:cd /tmp"
    assert conn.shell_calls == ["cd /tmp"]


async def test_mcpssherror_returns_structured_response(tmp_path):
    """MCPSSHError subclasses must not escape as raw exceptions (I1)."""
    conn = FakeConn()
    cfg = AppConfig(hosts={"h1": conn.cfg}, settings=Settings())
    from mcp_ssh.audit import AuditLogger

    class ErrorManager:
        async def get(self, host_name):
            raise ConnectionFailedError("Connection refused")

    state = server.AppState(
        config=cfg,
        manager=ErrorManager(),
        audit=AuditLogger(str(tmp_path / "audit.log")),
        config_path="/path/hosts.yaml",
        reload_interval=5,
    )
    server.set_state(state)
    out = await server.ssh_run("h1", "ls")
    assert "error" in out
    assert out["type"] == "ConnectionFailedError"
    assert "Connection refused" in out["error"]


async def test_host_not_found_returns_structured_response(tmp_path):
    """HostNotFoundError (MCPSSHError subclass) must return a structured dict (I1)."""
    conn = FakeConn()
    cfg = AppConfig(hosts={"h1": conn.cfg}, settings=Settings())
    from mcp_ssh.audit import AuditLogger
    from mcp_ssh.session_manager import SessionManager

    # Use the real SessionManager so that requesting an unknown host raises HostNotFoundError
    state = server.AppState(
        config=cfg,
        manager=SessionManager(cfg, {}),
        audit=AuditLogger(str(tmp_path / "audit.log")),
        config_path="/path/hosts.yaml",
        reload_interval=5,
    )
    server.set_state(state)
    out = await server.ssh_run("missing_host", "ls")
    assert "error" in out
    assert out["type"] == "HostNotFoundError"
