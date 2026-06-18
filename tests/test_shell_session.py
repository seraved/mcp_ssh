import pytest

from mcp_ssh.connection import SSHConnection
from mcp_ssh.models import Settings


@pytest.mark.integration
async def test_shell_preserves_state(integration_host, env):
    conn = SSHConnection("test", integration_host, Settings(), env)
    await conn.connect()
    try:
        await conn.run_in_shell("cd /tmp")
        result = await conn.run_in_shell("pwd")
        assert result.exit_code == 0
        assert "/tmp" in result.output
    finally:
        await conn.close()


@pytest.mark.integration
async def test_shell_timeout_keeps_session(integration_host, env):
    conn = SSHConnection("test", integration_host, Settings(), env)
    await conn.connect()
    try:
        slow = await conn.run_in_shell("sleep 5", timeout=1.0)
        assert slow.timed_out is True
        # session still usable after a timeout
        ok = await conn.run_in_shell("echo recovered")
        assert "recovered" in ok.output
    finally:
        await conn.close()
