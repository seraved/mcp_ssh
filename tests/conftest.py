import socket

import pytest

from mcp_ssh.models import AuthConfig, HostConfig

SSH_HOST = "127.0.0.1"
SSH_PORT = 2222


def _server_reachable() -> bool:
    try:
        with socket.create_connection((SSH_HOST, SSH_PORT), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture
def env():
    return {"TEST_SSH_PASS": "testpass"}


@pytest.fixture
def integration_host():
    return HostConfig(
        host=SSH_HOST,
        port=SSH_PORT,
        user="testuser",
        host_key_checking="off",
        auth=AuthConfig(method="password", password_env="TEST_SSH_PASS"),
    )


@pytest.fixture(autouse=True)
def require_ssh_server(request):
    if request.node.get_closest_marker("integration") and not _server_reachable():
        pytest.skip("docker-compose SSH server not reachable on 127.0.0.1:2222")
