import asyncio
from unittest.mock import MagicMock, patch

from mcp_ssh.models import AppConfig, HostConfig, AuthConfig, AuthMethod
from mcp_ssh.server import AppState, _config_reload_loop, set_state


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


def _make_config(host_names: list[str]) -> AppConfig:
    return AppConfig(hosts={
        name: HostConfig(
            host=f"{name}.example.com",
            user="admin",
            auth=AuthConfig(method=AuthMethod.key, key_path="~/.ssh/id_ed25519"),
        )
        for name in host_names
    })


def _make_state(config: AppConfig) -> AppState:
    manager = MagicMock()
    manager._config = config
    state = AppState(
        config=config,
        manager=manager,
        audit=MagicMock(),
        config_path="/fake/hosts.yaml",
        reload_interval=0,
    )
    set_state(state)
    return state


async def test_no_reload_when_mtime_unchanged():
    state = _make_state(_make_config(["host1"]))

    with patch("mcp_ssh.server.os.path.getmtime", return_value=1000.0), \
         patch("mcp_ssh.server.load_config") as mock_load:
        task = asyncio.create_task(_config_reload_loop("/fake/hosts.yaml", interval=0))
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    mock_load.assert_not_called()


async def test_reloads_config_when_mtime_changes():
    old_config = _make_config(["host1"])
    new_config = _make_config(["host1", "host2"])
    state = _make_state(old_config)

    # First call is init (1000.0); subsequent calls return 1001.0 → triggers reload once
    mtimes = [1000.0] + [1001.0] * 20
    with patch("mcp_ssh.server.os.path.getmtime", side_effect=mtimes), \
         patch("mcp_ssh.server.load_config", return_value=new_config):
        task = asyncio.create_task(_config_reload_loop("/fake/hosts.yaml", interval=0))
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert state.config is new_config
    assert state.manager._config is new_config


async def test_reload_error_preserves_old_config():
    old_config = _make_config(["host1"])
    state = _make_state(old_config)

    mtimes = [1000.0] + [1001.0] * 20
    with patch("mcp_ssh.server.os.path.getmtime", side_effect=mtimes), \
         patch("mcp_ssh.server.load_config", side_effect=ValueError("bad yaml")):
        task = asyncio.create_task(_config_reload_loop("/fake/hosts.yaml", interval=0))
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert state.config is old_config
    assert state.manager._config is old_config
