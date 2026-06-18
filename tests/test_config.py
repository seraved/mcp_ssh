import textwrap

import pytest

from mcp_ssh.config import load_config
from mcp_ssh.errors import MissingEnvError
from mcp_ssh.models import AuthMethod, ShellType


def _write(tmp_path, text):
    p = tmp_path / "hosts.yaml"
    p.write_text(textwrap.dedent(text))
    return str(p)


def test_load_valid_config(tmp_path):
    path = _write(tmp_path, """
        hosts:
          home-server:
            host: 192.168.1.10
            user: admin
            auth:
              method: key
              key_path: ~/.ssh/id_ed25519
        settings:
          idle_timeout: 120
    """)
    cfg = load_config(path, env={})
    assert cfg.hosts["home-server"].auth.method is AuthMethod.key
    assert cfg.hosts["home-server"].shell is ShellType.posix
    assert cfg.settings.idle_timeout == 120


def test_missing_password_env_raises(tmp_path):
    path = _write(tmp_path, """
        hosts:
          router1:
            host: 192.168.1.1
            user: cisco
            auth:
              method: password
              password_env: ROUTER1_PASS
    """)
    with pytest.raises(MissingEnvError) as exc:
        load_config(path, env={})
    assert exc.value.var_name == "ROUTER1_PASS"


def test_present_env_passes(tmp_path):
    path = _write(tmp_path, """
        hosts:
          router1:
            host: 192.168.1.1
            user: cisco
            auth:
              method: password
              password_env: ROUTER1_PASS
    """)
    cfg = load_config(path, env={"ROUTER1_PASS": "secret"})
    assert "router1" in cfg.hosts
