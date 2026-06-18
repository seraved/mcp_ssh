#!/usr/bin/env python3
"""Interactive CRUD manager for hosts.yaml."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def _make_yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.default_flow_style = False
    return y


def resolve_config_path() -> Path:
    env = os.environ.get("MCP_SSH_CONFIG")
    if env:
        return Path(env)
    return Path("hosts.yaml")


def load_yaml(path: Path) -> CommentedMap:
    if not path.exists():
        return CommentedMap({"hosts": CommentedMap(), "settings": CommentedMap()})
    y = _make_yaml()
    with open(path, encoding="utf-8") as fh:
        data = y.load(fh)
    if data is None:
        data = CommentedMap({"hosts": CommentedMap(), "settings": CommentedMap()})
    if "hosts" not in data or data["hosts"] is None:
        data["hosts"] = CommentedMap()
    return data


def save_yaml(data: CommentedMap, path: Path) -> None:
    y = _make_yaml()
    tmp = path.with_suffix(".yaml.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        y.dump(data, fh)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Validators (return True if valid, error string if not)
# ---------------------------------------------------------------------------

def validate_port(val: str) -> bool | str:
    try:
        n = int(val)
    except ValueError:
        return "Must be a number"
    if 1 <= n <= 65535:
        return True
    return "Port must be between 1 and 65535"


def validate_hostname(val: str) -> bool | str:
    v = val.strip()
    if not v:
        return "Required"
    if re.match(r"^[\w][\w.\-]*$", v):
        return True
    return "Invalid hostname (use letters, digits, dots, hyphens)"


def validate_regex(val: str) -> bool | str:
    v = val.strip()
    if not v:
        return "Required"
    try:
        re.compile(v)
        return True
    except re.error as e:
        return f"Invalid regex: {e}"


def validate_nonempty(val: str) -> bool | str:
    if val.strip():
        return True
    return "Required"


def warn_env_var(name: str) -> None:
    if name and name.strip() and name.strip() not in os.environ:
        print(f"\033[33mWarning: env var '{name.strip()}' not found in current environment.\033[0m")
