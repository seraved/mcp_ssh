from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

DEFAULT_DENY_PATTERNS = [
    r"rm\s+-rf\s+/",
    r"\bmkfs\b",
    r"\breboot\b",
    r"\bshutdown\b",
    r"dd\s+.*of=/dev/",
    r"\bwrite\s+erase\b",
    r"\berase\s+startup-config\b",
]


class AuthMethod(str, Enum):
    key = "key"
    password = "password"


class ShellType(str, Enum):
    posix = "posix"
    cli = "cli"


class AuthConfig(BaseModel):
    method: AuthMethod
    key_path: str | None = None
    passphrase_env: str | None = None
    password_env: str | None = None


class HostConfig(BaseModel):
    host: str
    port: int = 22
    user: str
    auth: AuthConfig
    shell: ShellType = ShellType.posix
    prompt_regex: str | None = None
    host_key_checking: str | None = None  # override of Settings.host_key_checking


class Settings(BaseModel):
    idle_timeout: int = 600
    command_timeout: int = 60
    keepalive_interval: int = 30
    max_output_bytes: int = 1048576
    host_key_checking: str = "strict"
    audit_log: str = "~/.mcp_ssh/audit.log"
    deny_patterns: list[str] = Field(default_factory=lambda: list(DEFAULT_DENY_PATTERNS))


class AppConfig(BaseModel):
    hosts: dict[str, HostConfig]
    settings: Settings = Field(default_factory=Settings)


class CommandResult(BaseModel):
    output: str
    stderr: str = ""
    exit_code: int | None = None
    duration: float = 0.0
    timed_out: bool = False
    truncated: bool = False
    hint: str | None = None


class BlockedResult(BaseModel):
    blocked: bool = True
    reason: str
    matched_pattern: str
    hint: str
