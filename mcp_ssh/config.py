from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

import yaml

from .errors import MissingEnvError
from .models import AppConfig


def default_config_path() -> str:
    env_path = os.environ.get("MCP_SSH_CONFIG")
    if env_path:
        return env_path
    return str(Path(__file__).resolve().parent / "hosts.yaml")


def load_config(path: str, env: Mapping[str, str] | None = None) -> AppConfig:
    if env is None:
        env = os.environ
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    config = AppConfig.model_validate(raw)
    _check_env_refs(config, env)
    return config


def _check_env_refs(config: AppConfig, env: Mapping[str, str]) -> None:
    for host in config.hosts.values():
        for var in (host.auth.password_env, host.auth.passphrase_env):
            if var and var not in env:
                raise MissingEnvError(var)
