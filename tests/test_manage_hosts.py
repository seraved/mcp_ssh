import os
import pytest
from pathlib import Path
from ruamel.yaml.comments import CommentedMap

# Add project root to path so manage_hosts is importable
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from manage_hosts import load_yaml, save_yaml, resolve_config_path


@pytest.fixture
def chdir(tmp_path):
    old = Path.cwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(old)


def test_load_yaml_existing(tmp_path):
    f = tmp_path / "hosts.yaml"
    f.write_text("hosts:\n  myhost:\n    host: 1.2.3.4\n    port: 22\n    user: admin\n    auth:\n      method: password\n      password_env: MY_PASS\n    shell: posix\nsettings: {}\n")
    data = load_yaml(f)
    assert "hosts" in data
    assert "myhost" in data["hosts"]


def test_load_yaml_missing_creates_empty_structure(tmp_path):
    f = tmp_path / "nonexistent.yaml"
    data = load_yaml(f)
    assert "hosts" in data
    assert data["hosts"] == {} or data["hosts"] is None or isinstance(data["hosts"], CommentedMap)


def test_save_yaml_roundtrip(tmp_path):
    f = tmp_path / "hosts.yaml"
    f.write_text("hosts:\n  myhost:\n    host: 1.2.3.4\n    port: 22\n    user: admin\n    auth:\n      method: password\n      password_env: MY_PASS\n    shell: posix\nsettings: {}\n")
    data = load_yaml(f)
    data["hosts"]["myhost"]["port"] = 2222
    save_yaml(data, f)
    data2 = load_yaml(f)
    assert data2["hosts"]["myhost"]["port"] == 2222


def test_save_yaml_atomic(tmp_path):
    """Temp file must not remain after save."""
    f = tmp_path / "hosts.yaml"
    f.write_text("hosts: {}\nsettings: {}\n")
    data = load_yaml(f)
    save_yaml(data, f)
    tmp = f.with_suffix(".yaml.tmp")
    assert not tmp.exists()


def test_resolve_config_path_env(tmp_path, monkeypatch):
    p = tmp_path / "custom.yaml"
    p.touch()
    monkeypatch.setenv("MCP_SSH_CONFIG", str(p))
    assert resolve_config_path() == p


def test_resolve_config_path_default(monkeypatch, tmp_path, chdir):
    monkeypatch.delenv("MCP_SSH_CONFIG", raising=False)
    # resolve_config_path returns Path("hosts.yaml") relative to cwd
    result = resolve_config_path()
    assert result.name == "hosts.yaml"
