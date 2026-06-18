import pytest
from pydantic import ValidationError

from mcp_ssh.models import (
    AppConfig, AuthConfig, AuthMethod, HostConfig, Settings, ShellType,
    CommandResult,
)
from mcp_ssh.errors import MissingEnvError


def test_settings_defaults():
    s = Settings()
    assert s.idle_timeout == 600
    assert s.command_timeout == 60
    assert s.keepalive_interval == 30
    assert s.max_output_bytes == 1048576
    assert s.host_key_checking == "strict"
    assert s.audit_log == "~/.mcp_ssh/audit.log"
    assert r"\breboot\b" in s.deny_patterns


def test_hostconfig_defaults_and_enums():
    h = HostConfig(host="1.2.3.4", user="root",
                   auth=AuthConfig(method="password", password_env="P"))
    assert h.port == 22
    assert h.shell is ShellType.posix
    assert h.auth.method is AuthMethod.password


def test_appconfig_requires_hosts():
    cfg = AppConfig(hosts={"h": HostConfig(
        host="1.2.3.4", user="root",
        auth=AuthConfig(method="key", key_path="~/.ssh/id_ed25519"))})
    assert "h" in cfg.hosts
    assert isinstance(cfg.settings, Settings)


def test_command_result_optional_exit_code():
    r = CommandResult(output="hi", duration=0.1)
    assert r.exit_code is None
    assert r.timed_out is False


def test_missing_env_error_carries_var_name():
    err = MissingEnvError("ROUTER1_PASS")
    assert "ROUTER1_PASS" in str(err)
