import pytest

from mcp_ssh.connection import build_connect_kwargs
from mcp_ssh.errors import MissingEnvError
from mcp_ssh.models import AuthConfig, HostConfig, Settings


def test_password_kwargs():
    cfg = HostConfig(host="h", user="u",
                     auth=AuthConfig(method="password", password_env="P"))
    kw = build_connect_kwargs(cfg, Settings(), {"P": "secret"})
    assert kw["host"] == "h"
    assert kw["port"] == 22
    assert kw["username"] == "u"
    assert kw["password"] == "secret"
    assert kw["keepalive_interval"] == 30


def test_password_missing_env():
    cfg = HostConfig(host="h", user="u",
                     auth=AuthConfig(method="password", password_env="P"))
    with pytest.raises(MissingEnvError):
        build_connect_kwargs(cfg, Settings(), {})


def test_key_kwargs_with_passphrase():
    cfg = HostConfig(host="h", user="u", auth=AuthConfig(
        method="key", key_path="~/.ssh/id_ed25519", passphrase_env="PP"))
    kw = build_connect_kwargs(cfg, Settings(), {"PP": "phrase"})
    assert kw["client_keys"] == ["~/.ssh/id_ed25519"]
    assert kw["passphrase"] == "phrase"
    assert "password" not in kw


def test_host_key_checking_off_disables_known_hosts():
    cfg = HostConfig(host="h", user="u", host_key_checking="off",
                     auth=AuthConfig(method="key", key_path="k"))
    kw = build_connect_kwargs(cfg, Settings(), {})
    assert kw["known_hosts"] is None


def test_host_key_checking_strict_omits_known_hosts():
    cfg = HostConfig(host="h", user="u",
                     auth=AuthConfig(method="key", key_path="k"))
    kw = build_connect_kwargs(cfg, Settings(host_key_checking="strict"), {})
    assert "known_hosts" not in kw
