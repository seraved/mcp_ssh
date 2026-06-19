# mcp-ssh Bug Fix Design — 2026-06-19

## Context

Two bugs blocking mcp-ssh in production Docker deployment.

---

## BUG-001 · Permission denied: /data/audit.log

### Root cause

`/opt/mcp-ssh/data` bind-mounted from host as `root:root 755`.
Container user `mcpssh` (uid=1000, gid=999) cannot write → every `ssh_run`/`ssh_shell` call fails before reaching SSH.

Dockerfile creates `/data` correctly during image build (`chown mcpssh:mcpssh /data`), but the bind mount at runtime overrides that with the host directory's ownership.

### Fix: entrypoint.sh with privilege drop

1. **Remove `USER mcpssh`** from Dockerfile — container starts as root so entrypoint can `chown`.
2. **Install `gosu`** in Dockerfile (apt-get, no cache).
3. **Add `docker-entrypoint.sh`** to repo root:

```sh
#!/bin/sh
set -e
chown mcpssh:mcpssh /data
exec gosu mcpssh "$@"
```

4. **Dockerfile** — copy script, make executable, set as `ENTRYPOINT`:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends gosu && rm -rf /var/lib/apt/lists/*
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "-m", "mcp_ssh.server"]
```

Remove `USER mcpssh` line — gosu handles the drop.

### What does NOT change

- `docker-compose.yml` volumes — no changes needed.
- `mcpssh` user still created with same uid/gid.
- Runtime process still runs as `mcpssh` after entrypoint drops privileges.

---

## BUG-002 · mcp-ssh tools not visible in Claude Code

### Root cause

Last commit switched server to `streamable_http_app()` (MCP protocol 2025-03-26, endpoint `/mcp`).
Claude Code currently supports SSE transport (`/sse` endpoint) — streamable-http is not loaded from `settings.json`.

### Fix: restore SSE transport, keep streamable-http as option

#### server.py changes

Restore `_run_sse_with_auth()` alongside `_run_http_with_auth()`. Both functions exist; `MCP_TRANSPORT` selects which runs:

```
MCP_TRANSPORT=sse  → _run_sse_with_auth()   → /sse  (FastMCP.sse_app)
MCP_TRANSPORT=http → _run_http_with_auth()  → /mcp  (FastMCP.streamable_http_app)
```

`_run_sse_with_auth()` restores the pre-bug implementation:

```python
def _run_sse_with_auth(host: str, port: int, auth_token: str) -> None:
    import uvicorn
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import Response

    class BearerAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            import hmac
            authorization = request.headers.get("Authorization", "")
            provided = authorization[7:] if authorization.startswith("Bearer ") else ""
            if not hmac.compare_digest(provided, auth_token):
                return Response("Unauthorized", status_code=401)
            return await call_next(request)

    sse_app = mcp.sse_app()
    app = Starlette(
        routes=sse_app.routes,
        middleware=[Middleware(BearerAuthMiddleware)],
    )
    uvicorn.run(app, host=host, port=port)
```

`main()` transport branch:
```python
if transport in ("sse", "http"):
    # ... auth check ...
    if transport == "http":
        _run_http_with_auth(host, port, auth_token)
    else:
        _run_sse_with_auth(host, port, auth_token)
```

#### docker-compose.yml

```yaml
MCP_TRANSPORT: sse   # was: http
```

Also remove the `SVEN_PASS` credential that was committed in plain text.

#### ~/.claude/settings.json — mcp-ssh entry

Update to SSE type and correct endpoint:
```json
"mcp-ssh": {
  "type": "sse",
  "url": "http://localhost:8000/sse",
  "headers": {
    "Authorization": "Bearer <MCP_AUTH_TOKEN>"
  }
}
```

---

## Files changed

| File | Change |
|---|---|
| `Dockerfile` | Remove `USER mcpssh`; install gosu; add ENTRYPOINT |
| `docker-entrypoint.sh` | New file — chown /data, exec gosu mcpssh |
| `mcp_ssh/server.py` | Restore `_run_sse_with_auth()`; fix transport branch |
| `docker-compose.yml` | `MCP_TRANSPORT: sse`; remove `SVEN_PASS` |
| `~/.claude/settings.json` | `type: sse`, URL `→ /sse` |

## Out of scope

- No changes to `hosts.yaml`, `models.py`, `safety.py`, tests.
- No refactor of middleware — only restore what was removed.

## Verification

After rebuild and restart:
1. `docker exec mcp-ssh ls -la /data/audit.log` — file exists, owned mcpssh.
2. `docker exec mcp-ssh id` — shows uid=1000(mcpssh).
3. MCP call `ssh_run` on any host → no permission error.
4. Restart Claude Code → `ssh_run`, `ssh_connect` etc. appear in tool list.
