import time

import pytest

from mcp_ssh.errors import HostNotFoundError
from mcp_ssh.models import AppConfig, AuthConfig, HostConfig, Settings
from mcp_ssh.session_manager import SessionManager


class FakeConn:
    def __init__(self, name, cfg, settings, env):
        self.name = name
        self.last_used = time.monotonic()
        self.connected = False
        self.closed = False
        self._alive = False

    @property
    def is_alive(self):
        return self._alive

    async def connect(self):
        self.connected = True
        self._alive = True

    async def close(self):
        self.closed = True
        self._alive = False


def _config():
    return AppConfig(
        hosts={"h1": HostConfig(host="x", user="u",
                                auth=AuthConfig(method="key", key_path="k"))},
        settings=Settings(idle_timeout=10),
    )


async def test_get_creates_and_connects():
    mgr = SessionManager(_config(), env={}, connection_factory=FakeConn)
    conn = await mgr.get("h1")
    assert conn.connected is True
    # second call reuses the same object
    assert await mgr.get("h1") is conn


async def test_get_unknown_host():
    mgr = SessionManager(_config(), env={}, connection_factory=FakeConn)
    with pytest.raises(HostNotFoundError) as exc:
        await mgr.get("nope")
    assert "h1" in str(exc.value)


async def test_reap_idle_closes_old():
    mgr = SessionManager(_config(), env={}, connection_factory=FakeConn)
    conn = await mgr.get("h1")
    conn.last_used = time.monotonic() - 100  # older than idle_timeout=10
    closed = await mgr.reap_idle()
    assert closed == ["h1"]
    assert conn.closed is True


async def test_disconnect_and_list():
    mgr = SessionManager(_config(), env={}, connection_factory=FakeConn)
    await mgr.get("h1")
    assert any(s["host"] == "h1" for s in mgr.list_sessions())
    assert await mgr.disconnect("h1") is True
    assert mgr.list_sessions() == []
