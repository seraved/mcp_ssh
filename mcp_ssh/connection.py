from __future__ import annotations

from collections.abc import Mapping

from .errors import MissingEnvError
from .models import AuthMethod, HostConfig, Settings


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
    else:
        kwargs["client_keys"] = [cfg.auth.key_path]
        if cfg.auth.passphrase_env:
            kwargs["passphrase"] = _require_env(env, cfg.auth.passphrase_env)
    return kwargs
