import pytest

from mcp_ssh.connection import SSHConnection


@pytest.mark.integration
async def test_exec_echo(integration_host, env):
    conn = SSHConnection("test", integration_host, _settings(), env)
    await conn.connect()
    try:
        result = await conn.run_exec("echo hello")
        assert result.exit_code == 0
        assert "hello" in result.output
    finally:
        await conn.close()


@pytest.mark.integration
async def test_exec_nonzero_exit(integration_host, env):
    conn = SSHConnection("test", integration_host, _settings(), env)
    await conn.connect()
    try:
        result = await conn.run_exec("exit 3")
        assert result.exit_code == 3
    finally:
        await conn.close()


def _settings():
    from mcp_ssh.models import Settings
    return Settings()
