# mcp-ssh

MCP server for running commands over persistent SSH sessions. Connects AI assistants (Claude, Cursor, etc.) to remote hosts — Linux servers, routers, switches, and any SSH-accessible device.

> Built with the help of Claude AI (Anthropic).

---

## Features

- **Persistent SSH sessions** — connections are pooled and reused; no reconnect overhead per command
- **Two execution modes** — stateless `exec` for POSIX hosts, stateful PTY shell for interactive CLIs (Cisco, MikroTik, etc.)
- **Safety layer** — configurable regex deny-list blocks destructive commands (`rm -rf /`, `mkfs`, `reboot`, etc.)
- **Append-only audit log** — every command, decision, and exit code recorded to JSONL
- **Two transports** — `stdio` for local use, `SSE` with Bearer token auth for remote/Docker deployment
- **No secrets in config** — passwords and passphrases are referenced by environment variable name, not stored

## MCP Tools

| Tool | Description |
|---|---|
| `ssh_list_hosts` | List configured hosts (no secrets exposed) |
| `ssh_connect` | Open or reuse a persistent session |
| `ssh_run` | Run a stateless command via exec (POSIX) |
| `ssh_shell` | Run a command in the interactive PTY shell (stateful, required for CLI devices) |
| `ssh_list_sessions` | Show active sessions and idle times |
| `ssh_disconnect` | Close a session |

All tools accept `confirm_dangerous=true` to override a safety block when the command is intentional.

## Quick Start

### Install

```bash
git clone https://github.com/your-username/mcp-ssh
cd mcp-ssh
poetry config virtualenvs.in-project true --local
poetry install
```

### Configure hosts

Use the interactive manager to add, edit, or remove hosts without touching YAML by hand:

```bash
python manage_hosts.py
# or with an explicit config path:
MCP_SSH_CONFIG=/path/to/hosts.yaml python manage_hosts.py
```

The script provides a menu-driven terminal UI: list hosts, add, edit (current values shown as defaults), and delete with confirmation. Validates IP/hostname, port range, regex syntax, and warns if a referenced env var is not exported.

Alternatively, copy `hosts.example.yaml` and edit manually:

```yaml
hosts:
  home-server:
    host: 192.168.1.10
    user: admin
    auth:
      method: key
      key_path: ~/.ssh/id_ed25519
    shell: posix

  cisco-switch:
    host: 192.168.1.1
    user: cisco
    auth:
      method: password
      password_env: CISCO_PASS      # name of env var, not the password itself
    shell: cli
    prompt_regex: '[\w.-]+[>#]\s*$'

settings:
  idle_timeout: 600
  command_timeout: 60
  audit_log: ~/.mcp_ssh/audit.log
```

Export secrets before starting:

```bash
export MCP_SSH_CONFIG=/path/to/hosts.yaml
export CISCO_PASS='my-password'
```

### Run (stdio — local use)

```bash
poetry run mcp-ssh
```

Register `poetry run mcp-ssh` (with env vars set) as a stdio MCP server in your AI assistant.

### Run (SSE — remote / Docker)

```bash
export MCP_TRANSPORT=sse
export MCP_AUTH_TOKEN=$(python -c "import secrets; print(secrets.token_hex(32))")
export MCP_PORT=8000
poetry run mcp-ssh
```

`MCP_HOST` defaults to `127.0.0.1`. Set `MCP_HOST=0.0.0.0` only when a reverse proxy handles TLS and auth in front.

## Shell Types

| Device | `shell` | Reason |
|---|---|---|
| Linux / Raspberry Pi | `posix` | Standard POSIX shell, has `echo $?` |
| OpenWRT / DD-WRT | `posix` | BusyBox ash — POSIX compatible |
| Cisco IOS / NX-OS | `cli` | Proprietary CLI, no `$?` |
| MikroTik RouterOS | `cli` | Proprietary CLI |
| Managed switches | `cli` | Proprietary CLI |

`cli` hosts require `prompt_regex` — a regex matching the device prompt (e.g. `[\w.-]+[>#]\s*$`).

## Safety

Default deny patterns block:

```
rm -rf /      mkfs      reboot      shutdown
dd of=/dev/*  write erase   erase startup-config
```

Extend or override in `hosts.yaml`:

```yaml
settings:
  deny_patterns:
    - "rm\\s+-rf\\s+/"
    - "your-custom-pattern"
```

Pass `confirm_dangerous=true` to any tool to override a block when you know it is intentional.

## Docker / Portainer

See [docs/portainer-deployment.md](docs/portainer-deployment.md) for a full guide including nginx reverse proxy setup.

```bash
docker compose up -d
```

Key environment variables for the container:

| Variable | Required | Default | Description |
|---|---|---|---|
| `MCP_SSH_CONFIG` | yes | — | Path to `hosts.yaml` inside the container |
| `MCP_TRANSPORT` | no | `stdio` | Set to `sse` for HTTP transport |
| `MCP_AUTH_TOKEN` | yes (SSE) | — | Bearer token; required in SSE mode |
| `MCP_HOST` | no | `127.0.0.1` | Bind address |
| `MCP_PORT` | no | `8000` | Bind port |

## Tests

```bash
# Unit tests (no Docker required)
poetry run pytest -m "not integration"

# Full suite (requires docker-compose SSH server)
docker compose up -d
poetry run pytest
docker compose down
```

## Architecture

```
AI Agent (Claude / Cursor)
    │  stdio or HTTP SSE + Bearer token
    ▼
mcp-ssh server
    ├── safety.classify_command()   ← regex deny-list
    ├── audit.log()                 ← append-only JSONL
    └── SessionManager.get()        ← pooled SSH connections
            ├── SSHConnection.run_exec()      ← POSIX stateless
            └── SSHConnection.run_in_shell()  ← PTY stateful (ShellSession)
```

Key modules: [mcp_ssh/server.py](mcp_ssh/server.py) · [mcp_ssh/session_manager.py](mcp_ssh/session_manager.py) · [mcp_ssh/connection.py](mcp_ssh/connection.py) · [mcp_ssh/safety.py](mcp_ssh/safety.py) · [mcp_ssh/audit.py](mcp_ssh/audit.py)

## License

MIT
