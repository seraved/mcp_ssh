import pytest

from mcp_ssh import server
from mcp_ssh.audit import AuditLogger
from mcp_ssh.models import AppConfig, Settings
from mcp_ssh.session_manager import SessionManager


@pytest.mark.integration
async def test_end_to_end_run_and_reuse(tmp_path, integration_host, env):
    config = AppConfig(hosts={"h1": integration_host}, settings=Settings())
    manager = SessionManager(config, env)
    server.set_state(server.AppState(
        config=config, manager=manager,
        audit=AuditLogger(str(tmp_path / "audit.log"))))
    try:
        out = await server.ssh_run("h1", "echo e2e")
        assert out["exit_code"] == 0
        assert "e2e" in out["output"]
        # session reuse: shell keeps state across calls
        await server.ssh_shell("h1", "cd /tmp")
        pwd = await server.ssh_shell("h1", "pwd")
        assert "/tmp" in pwd["output"]
    finally:
        await server.ssh_disconnect("h1")
