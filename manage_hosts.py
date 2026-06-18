#!/usr/bin/env python3
"""Interactive CRUD manager for hosts.yaml."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

import questionary


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


# ---------------------------------------------------------------------------
# UI operations
# ---------------------------------------------------------------------------

def do_list(data: CommentedMap) -> None:
    hosts = data.get("hosts") or {}
    if not hosts:
        print("No hosts configured.")
        return
    fmt = "{:<20} {:<24} {:<12} {:<10} {:<8}"
    print(fmt.format("ALIAS", "HOST:PORT", "USER", "AUTH", "SHELL"))
    print("-" * 76)
    for alias, h in hosts.items():
        port = h.get("port", 22)
        auth = h.get("auth", {}).get("method", "?")
        shell = h.get("shell", "posix")
        print(fmt.format(alias, f"{h['host']}:{port}", h["user"], auth, shell))


def do_add(data: CommentedMap, path: Path) -> None:
    hosts = data.setdefault("hosts", CommentedMap())
    existing = list(hosts.keys())

    def validate_alias(val: str) -> bool | str:
        v = val.strip()
        if not v:
            return "Required"
        if v in existing:
            return f"Alias '{v}' already exists"
        return True

    alias = questionary.text("Alias (name in yaml):", validate=validate_alias).ask()
    if alias is None:
        return
    alias = alias.strip()

    host = questionary.text("Host (IP or hostname):", validate=validate_hostname).ask()
    if host is None:
        return

    port = questionary.text("Port:", default="22", validate=validate_port).ask()
    if port is None:
        return

    user = questionary.text("User:", validate=validate_nonempty).ask()
    if user is None:
        return

    auth_method = questionary.select("Auth method:", choices=["key", "password"]).ask()
    if auth_method is None:
        return

    auth: dict = {"method": auth_method}

    if auth_method == "key":
        key_path = questionary.text("Key path:", default="~/.ssh/id_ed25519",
                                    validate=validate_nonempty).ask()
        if key_path is None:
            return
        auth["key_path"] = key_path.strip()

        passphrase_env = questionary.text(
            "Passphrase env var (leave blank if none):", default=""
        ).ask()
        if passphrase_env is None:
            return
        if passphrase_env.strip():
            auth["passphrase_env"] = passphrase_env.strip()
            warn_env_var(passphrase_env)
    else:
        password_env = questionary.text("Password env var:", validate=validate_nonempty).ask()
        if password_env is None:
            return
        auth["password_env"] = password_env.strip()
        warn_env_var(password_env)

    shell = questionary.select("Shell type:", choices=["posix", "cli"]).ask()
    if shell is None:
        return

    entry: dict = {
        "host": host.strip(),
        "port": int(port),
        "user": user.strip(),
        "auth": auth,
        "shell": shell,
    }

    if shell == "cli":
        prompt_regex = questionary.text(
            "Prompt regex:", validate=validate_regex
        ).ask()
        if prompt_regex is None:
            return
        entry["prompt_regex"] = prompt_regex.strip()

    hosts[alias] = CommentedMap(entry)
    save_yaml(data, path)
    print(f"\nHost '{alias}' added.")


def do_edit(data: CommentedMap, path: Path) -> None:
    hosts = data.get("hosts") or {}
    if not hosts:
        print("No hosts configured.")
        return

    alias = questionary.select("Select host to edit:", choices=list(hosts.keys())).ask()
    if alias is None:
        return

    h = hosts[alias]
    old_auth = h.get("auth", {})

    host = questionary.text(
        "Host:", default=str(h.get("host", "")), validate=validate_hostname
    ).ask()
    if host is None:
        return

    port = questionary.text(
        "Port:", default=str(h.get("port", 22)), validate=validate_port
    ).ask()
    if port is None:
        return

    user = questionary.text(
        "User:", default=str(h.get("user", "")), validate=validate_nonempty
    ).ask()
    if user is None:
        return

    current_method = old_auth.get("method", "password")
    auth_method = questionary.select(
        "Auth method:",
        choices=["key", "password"],
        default=current_method,
    ).ask()
    if auth_method is None:
        return

    auth: dict = {"method": auth_method}

    if auth_method == "key":
        key_path = questionary.text(
            "Key path:",
            default=str(old_auth.get("key_path", "~/.ssh/id_ed25519")),
            validate=validate_nonempty,
        ).ask()
        if key_path is None:
            return
        auth["key_path"] = key_path.strip()

        passphrase_env = questionary.text(
            "Passphrase env var (leave blank if none):",
            default=str(old_auth.get("passphrase_env", "")),
        ).ask()
        if passphrase_env is None:
            return
        if passphrase_env.strip():
            auth["passphrase_env"] = passphrase_env.strip()
            warn_env_var(passphrase_env)
    else:
        password_env = questionary.text(
            "Password env var:",
            default=str(old_auth.get("password_env", "")),
            validate=validate_nonempty,
        ).ask()
        if password_env is None:
            return
        auth["password_env"] = password_env.strip()
        warn_env_var(password_env)

    current_shell = str(h.get("shell", "posix"))
    shell = questionary.select(
        "Shell type:", choices=["posix", "cli"], default=current_shell
    ).ask()
    if shell is None:
        return

    entry = CommentedMap({
        "host": host.strip(),
        "port": int(port),
        "user": user.strip(),
        "auth": auth,
        "shell": shell,
    })

    if shell == "cli":
        prompt_regex = questionary.text(
            "Prompt regex:",
            default=str(h.get("prompt_regex", "")),
            validate=validate_regex,
        ).ask()
        if prompt_regex is None:
            return
        entry["prompt_regex"] = prompt_regex.strip()

    hosts[alias] = entry
    save_yaml(data, path)
    print(f"\nHost '{alias}' updated.")
