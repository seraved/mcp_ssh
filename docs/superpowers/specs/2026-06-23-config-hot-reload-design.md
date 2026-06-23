# Config Hot-Reload Design

**Date:** 2026-06-23  
**Status:** Approved

## Problem

`AppState.config` is loaded once at startup. Adding a host via `manage_hosts.py` writes `hosts.yaml` but the running server never sees the change — a container restart is required.

## Goal

Server auto-detects changes to `hosts.yaml` and reloads config without restart.

## Approach: mtime polling

Background asyncio task polls `os.path.getmtime(config_path)` every N seconds. On change, calls `load_config()` and updates in-memory state.

**No new dependencies.** Delay = poll interval (default 5s).

## Architecture

### New: `_config_reload_loop(path, interval)` in `server.py`

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
            added = new_hosts - old_hosts
            removed = old_hosts - new_hosts
            parts = []
            if added:
                parts.append(f"+{','.join(sorted(added))}")
            if removed:
                parts.append(f"-{','.join(sorted(removed))}")
            delta = " ".join(parts) or "no host changes"
            print(f"[mcp-ssh] config reloaded: {delta}", flush=True, file=sys.stderr)
        except Exception as exc:
            print(f"[mcp-ssh] config reload failed: {exc}", flush=True, file=sys.stderr)
```

### `_lifespan` change

Add second task alongside existing `_reap_loop`:

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

### `AppState` change

Add `config_path` and `reload_interval` fields:

```python
@dataclass
class AppState:
    config: AppConfig
    manager: SessionManager
    audit: AuditLogger
    config_path: str
    reload_interval: int
```

### `main()` change

Read `MCP_RELOAD_INTERVAL` env var:

```python
reload_interval = int(os.environ.get("MCP_RELOAD_INTERVAL", "5"))
set_state(AppState(
    config=config,
    manager=manager,
    audit=audit,
    config_path=config_path,
    reload_interval=reload_interval,
))
```

## Why both `_state.config` and `_state.manager._config` must be updated

- `_execute()` reads `state.config.settings.deny_patterns` via `_get_state()`
- `SessionManager.get()` looks up hosts in `self._config.hosts` (its own reference, line 20)
- Both must point to the new `AppConfig` object

Assignment in asyncio event loop is safe — single-threaded, no interleaving.

## Error handling

| Error | Behavior |
|---|---|
| File not found / unreadable | Log warning, keep old config |
| Invalid YAML | Log warning, keep old config |
| `MissingEnvError` (new host refs unset env var) | Log warning, keep old config |

New config is never partially applied — assignment happens only after `load_config()` succeeds.

## Configuration

| Env var | Default | Description |
|---|---|---|
| `MCP_RELOAD_INTERVAL` | `5` | Poll interval in seconds |

## Scope

- Changes: `mcp_ssh/server.py` only
- No changes to `SessionManager`, `models.py`, `config.py`
- No new dependencies
