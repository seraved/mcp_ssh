from unittest.mock import MagicMock
from mcp_ssh.server import AppState


def test_appstate_has_config_path_and_reload_interval():
    state = AppState(
        config=MagicMock(),
        manager=MagicMock(),
        audit=MagicMock(),
        config_path="/path/hosts.yaml",
        reload_interval=10,
    )
    assert state.config_path == "/path/hosts.yaml"
    assert state.reload_interval == 10
