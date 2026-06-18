from __future__ import annotations

import time
from collections.abc import Mapping

from .connection import SSHConnection
from .errors import HostNotFoundError
from .models import AppConfig


class SessionManager:
    def __init__(self, config: AppConfig, env: Mapping[str, str],
                 connection_factory=SSHConnection):
        self._config = config
        self._env = env
        self._factory = connection_factory
        self._sessions: dict = {}

    async def get(self, host_name: str):
        if host_name not in self._config.hosts:
            available = ", ".join(sorted(self._config.hosts)) or "(none)"
            raise HostNotFoundError(
                f"Unknown host '{host_name}'. Available hosts: {available}")
        conn = self._sessions.get(host_name)
        if conn is not None and conn.is_alive:
            conn.last_used = time.monotonic()
            return conn
        cfg = self._config.hosts[host_name]
        conn = self._factory(host_name, cfg, self._config.settings, self._env)
        await conn.connect()
        self._sessions[host_name] = conn
        return conn

    async def disconnect(self, host_name: str) -> bool:
        conn = self._sessions.pop(host_name, None)
        if conn is None:
            return False
        await conn.close()
        return True

    def list_sessions(self) -> list[dict]:
        now = time.monotonic()
        return [
            {"host": name, "idle_seconds": round(now - conn.last_used, 1)}
            for name, conn in self._sessions.items()
        ]

    async def reap_idle(self) -> list[str]:
        now = time.monotonic()
        timeout = self._config.settings.idle_timeout
        stale = [name for name, conn in self._sessions.items()
                 if now - conn.last_used > timeout]
        for name in stale:
            await self.disconnect(name)
        return stale

    async def close_all(self) -> None:
        for name in list(self._sessions):
            await self.disconnect(name)
