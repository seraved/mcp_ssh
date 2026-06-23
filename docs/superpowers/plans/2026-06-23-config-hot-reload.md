# Config Hot-Reload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Server auto-detects changes to `hosts.yaml` and reloads config (hosts + settings) without restart.

**Architecture:** A background asyncio task polls `os.path.getmtime()` every N seconds. On mtime change it calls `load_config()` and atomically updates `_state.config` and `_state.manager._config`. Errors are logged; old config is preserved.

**Tech Stack:** Python stdlib only (`asyncio`, `os`). No new dependencies.

## Global Constraints

- Only `mcp_ssh/server.py` changes (+ new test file)
- No new dependencies
- `asyncio_mode = "auto"` in pytest config — no `@pytest.mark.asyncio` decorator needed
- Never partially apply a new config — assign only after `load_config()` succeeds

---

### Task 1: Extend AppState + update main()

**Files:**
- Modify: `mcp_ssh/server.py`
- Test: `tests/test_config_reload.py` (create)

**Interfaces:**
- Produces: `AppState` with fields `config_path: str`, `reload_interval: int`

- [ ] **Step 1: Write failing test**

Create `tests/test_config_reload.py`:

```python
from unittest.mock import MagicMock
from mcp_ssh.server import AppState


def test_appstate_has_config_path_and_reload_interval():
    state = AppState(
        config=MagicMock(),
        manager=MagicMock(),
        audit=MagicMock(),
        config_path="/path/hosts.yaml",
        reload_interval=10,
    )
    assert state.config_path == "/path/hosts.yaml"
    assert state.reload_interval == 10
```

- [ ] **Step 2: Run test — verify it fails**

```bash
poetry run pytest tests/test_config_reload.py -v
```

Expected: `TypeError: AppState.__init__() got unexpected keyword argument 'config_path'`

- [ ] **Step 3: Add fields to AppState and update main()**

In `mcp_ssh/server.py`, replace:

```python
import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
```

with:

```python
import asyncio
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
```

Replace the `AppState` dataclass:

```python
@dataclass
class AppState:
    config: AppConfig
    manager: object
    audit: AuditLogger
```

with:

```python
@dataclass
class AppState:
    config: AppConfig
    manager: object
    audit: AuditLogger
    config_path: str
    reload_interval: int
```

Replace the body of `main()`:

```python
def main() -> None:
    config = load_config(default_config_path(), os.environ)
    if audit_log_env := os.environ.get("MCP_AUDIT_LOG"):
        config.settings.audit_log = audit_log_env
    manager = SessionManager(config, os.environ)
    audit = AuditLogger(config.settings.audit_log)
    set_state(AppState(config=config, manager=manager, audit=audit))
```

with:

```python
def main() -> None:
    config_path = default_config_path()
    config = load_config(config_path, os.environ)
    if audit_log_env := os.environ.get("MCP_AUDIT_LOG"):
        config.settings.audit_log = audit_log_env
    reload_interval = int(os.environ.get("MCP_RELOAD_INTERVAL", "5"))
    manager = SessionManager(config, os.environ)
    audit = AuditLogger(config.settings.audit_log)
    set_state(AppState(
        config=config,
        manager=manager,
        audit=audit,
        config_path=config_path,
        reload_interval=reload_interval,
    ))
```

- [ ] **Step 4: Run test — verify it passes**

```bash
poetry run pytest tests/test_config_reload.py -v
```

Expected: `PASSED`

- [ ] **Step 5: Run existing suite — verify nothing broke**

```bash
poetry run pytest -m "not integration" -v
```

Expected: all passing (same count as before)

- [ ] **Step 6: Commit**

```bash
git add mcp_ssh/server.py tests/test_config_reload.py
git commit -m "feat(server): add config_path and reload_interval to AppState"
```

---

### Task 2: Implement `_config_reload_loop`

**Files:**
- Modify: `mcp_ssh/server.py`
- Modify: `tests/test_config_reload.py`

**Interfaces:**
- Consumes: `AppState.config_path: str`, `AppState.reload_interval: int`, `_get_state() -> AppState`, `load_config(path: str) -> AppConfig`
- Produces: `_config_reload_loop(path: str, interval: int = 5) -> Coroutine`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_config_reload.py`:

```python
import asyncio
from unittest.mock import MagicMock, patch

from mcp_ssh.models import AppConfig, HostConfig, AuthConfig, AuthMethod
from mcp_ssh.server import AppState, _config_reload_loop, set_state


def _make_config(host_names: list[str]) -> AppConfig:
    return AppConfig(hosts={
        name: HostConfig(
            host=f"{name}.example.com",
            user="admin",
            auth=AuthConfig(method=AuthMethod.key, key_path="~/.ssh/id_ed25519"),
        )
        for name in host_names
    })


def _make_state(config: AppConfig) -> AppState:
    manager = MagicMock()
    manager._config = config
    state = AppState(
        config=config,
        manager=manager,
        audit=MagicMock(),
        config_path="/fake/hosts.yaml",
        reload_interval=0,
    )
    set_state(state)
    return state


async def test_no_reload_when_mtime_unchanged():
    state = _make_state(_make_config(["host1"]))

    with patch("mcp_ssh.server.os.path.getmtime", return_value=1000.0), \
         patch("mcp_ssh.server.load_config") as mock_load:
        task = asyncio.create_task(_config_reload_loop("/fake/hosts.yaml", interval=0))
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    mock_load.assert_not_called()


async def test_reloads_config_when_mtime_changes():
    old_config = _make_config(["host1"])
    new_config = _make_config(["host1", "host2"])
    state = _make_state(old_config)

    # First call is init (1000.0); subsequent calls return 1001.0 → triggers reload once
    mtimes = [1000.0] + [1001.0] * 20
    with patch("mcp_ssh.server.os.path.getmtime", side_effect=mtimes), \
         patch("mcp_ssh.server.load_config", return_value=new_config):
        task = asyncio.create_task(_config_reload_loop("/fake/hosts.yaml", interval=0))
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert state.config is new_config
    assert state.manager._config is new_config


async def test_reload_error_preserves_old_config():
    old_config = _make_config(["host1"])
    state = _make_state(old_config)

    mtimes = [1000.0] + [1001.0] * 20
    with patch("mcp_ssh.server.os.path.getmtime", side_effect=mtimes), \
         patch("mcp_ssh.server.load_config", side_effect=ValueError("bad yaml")):
        task = asyncio.create_task(_config_reload_loop("/fake/hosts.yaml", interval=0))
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert state.config is old_config
    assert state.manager._config is old_config
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
poetry run pytest tests/test_config_reload.py -v
```

Expected: `ImportError: cannot import name '_config_reload_loop' from 'mcp_ssh.server'`

- [ ] **Step 3: Implement `_config_reload_loop` in server.py**

Add after the `_reap_loop` function (after line `await manager.reap_idle()`):

```python
async def _config_reload_loop(path: str, interval: int = 5) -> None:
    mtime = os.path.getmtime(path)
    while True:
        await asyncio.sleep(interval)
        try:
            new_mtime = os.path.getmtime(path)
            if new_mtime == mtime:
                continue
            new_config = load_config(path)
            state = _get_state()
            old_hosts = set(state.config.hosts)
            new_hosts = set(new_config.hosts)
            state.config = new_config
            state.manager._config = new_config
            mtime = new_mtime
            parts = []
            added = new_hosts - old_hosts
            removed = old_hosts - new_hosts
            if added:
                parts.append(f"+{','.join(sorted(added))}")
            if removed:
                parts.append(f"-{','.join(sorted(removed))}")
            delta = " ".join(parts) or "no host changes"
            print(f"[mcp-ssh] config reloaded: {delta}", flush=True, file=sys.stderr)
        except Exception as exc:
            print(f"[mcp-ssh] config reload failed: {exc}", flush=True, file=sys.stderr)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
poetry run pytest tests/test_config_reload.py -v
```

Expected: all 4 tests `PASSED`

- [ ] **Step 5: Run full suite**

```bash
poetry run pytest -m "not integration" -v
```

Expected: all passing

- [ ] **Step 6: Commit**

```bash
git add mcp_ssh/server.py tests/test_config_reload.py
git commit -m "feat(server): implement _config_reload_loop for hot config reload"
```

---

### Task 3: Wire `_config_reload_loop` into `_lifespan`

**Files:**
- Modify: `mcp_ssh/server.py`

**Interfaces:**
- Consumes: `_config_reload_loop(path: str, interval: int)`, `AppState.config_path: str`, `AppState.reload_interval: int`

- [ ] **Step 1: Replace `_lifespan` in server.py**

Replace:

```python
@asynccontextmanager
async def _lifespan(server):
    state = _get_state()
    task = asyncio.create_task(_reap_loop(state.manager))
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await state.manager.close_all()
```

with:

```python
@asynccontextmanager
async def _lifespan(server):
    state = _get_state()
    reap_task = asyncio.create_task(_reap_loop(state.manager))
    reload_task = asyncio.create_task(
        _config_reload_loop(state.config_path, state.reload_interval)
    )
    try:
        yield
    finally:
        reap_task.cancel()
        reload_task.cancel()
        await asyncio.gather(reap_task, reload_task, return_exceptions=True)
        await state.manager.close_all()
```

- [ ] **Step 2: Run full suite**

```bash
poetry run pytest -m "not integration" -v
```

Expected: all passing

- [ ] **Step 3: Smoke test (manual)**

```bash
export MCP_SSH_CONFIG=/tmp/test_hosts.yaml
echo "hosts: {}" > /tmp/test_hosts.yaml
poetry run mcp-ssh &
# wait 2s, then add a host
sleep 2
cat >> /tmp/test_hosts.yaml << 'EOF'
hosts:
  myhost:
    host: 192.168.1.1
    user: admin
    auth:
      method: key
      key_path: ~/.ssh/id_ed25519
    shell: posix
EOF
# within 5s should see: [mcp-ssh] config reloaded: +myhost
```

- [ ] **Step 4: Commit**

```bash
git add mcp_ssh/server.py
git commit -m "feat(server): wire config hot-reload into lifespan"
```
