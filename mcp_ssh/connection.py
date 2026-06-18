from __future__ import annotations

import time
from collections.abc import Mapping

import asyncssh

from .errors import AuthError, ConnectionFailedError, HostKeyError, MissingEnvError
from .models import AuthMethod, CommandResult, HostConfig, Settings
from .parsers import truncate_output


def _require_env(env: Mapping[str, str], var: str) -> str:
    if var not in env:
        raise MissingEnvError(var)
    return env[var]


def build_connect_kwargs(
    cfg: HostConfig, settings: Settings, env: Mapping[str, str]
) -> dict:
    kwargs: dict = {
        "host": cfg.host,
        "port": cfg.port,
        "username": cfg.user,
        "keepalive_interval": settings.keepalive_interval,
    }
    effective_hkc = cfg.host_key_checking or settings.host_key_checking
    if effective_hkc == "off":
        kwargs["known_hosts"] = None

    if cfg.auth.method is AuthMethod.password:
        kwargs["password"] = _require_env(env, cfg.auth.password_env)
        kwargs["agent_path"] = None
    else:
        kwargs["client_keys"] = [cfg.auth.key_path]
        if cfg.auth.passphrase_env:
            kwargs["passphrase"] = _require_env(env, cfg.auth.passphrase_env)
    return kwargs


class SSHConnection:
    def __init__(self, name, cfg, settings, env):
        self.name = name
        self.cfg = cfg
        self.settings = settings
        self.env = env
        self._conn = None
        self._shell = None
        self.last_used = time.monotonic()

    @property
    def is_alive(self) -> bool:
        return self._conn is not None and not self._conn.is_closed()

    async def connect(self) -> None:
        kwargs = build_connect_kwargs(self.cfg, self.settings, self.env)
        try:
            self._conn = await asyncssh.connect(**kwargs)
        except asyncssh.PermissionDenied as exc:
            raise AuthError(f"Authentication failed for host '{self.name}'") from exc
        except asyncssh.HostKeyNotVerifiable as exc:
            raise HostKeyError(
                f"Host key verification failed for '{self.name}' "
                f"({self.cfg.host}:{self.cfg.port})"
            ) from exc
        except (OSError, asyncssh.Error) as exc:
            raise ConnectionFailedError(
                f"Could not connect to '{self.name}' "
                f"({self.cfg.host}:{self.cfg.port}): {exc}"
            ) from exc
        self.last_used = time.monotonic()

    async def run_exec(self, command: str, timeout: float | None = None) -> CommandResult:
        if timeout is None:
            timeout = self.settings.command_timeout
        self.last_used = time.monotonic()
        start = time.monotonic()
        try:
            proc = await self._conn.run(command, timeout=timeout)
        except asyncssh.TimeoutError:
            return CommandResult(
                output="",
                duration=time.monotonic() - start,
                timed_out=True,
                hint=f"Command did not finish within {timeout}s.",
            )
        out, truncated = truncate_output(proc.stdout or "", self.settings.max_output_bytes)
        err, _ = truncate_output(proc.stderr or "", self.settings.max_output_bytes)
        self.last_used = time.monotonic()
        return CommandResult(
            output=out,
            stderr=err,
            exit_code=proc.exit_status,
            duration=time.monotonic() - start,
            truncated=truncated,
        )

    async def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            await self._conn.wait_closed()
            self._conn = None
