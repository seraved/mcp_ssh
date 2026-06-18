# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install
poetry config virtualenvs.in-project true --local
poetry install

# Tests
docker compose -f docker-compose-test.yml up -d   # start test SSH server (required for integration tests)
poetry run pytest -m "not integration"            # fast unit tests only
poetry run pytest                                 # full suite (requires docker compose)
poetry run pytest tests/test_safety.py            # single test file
docker compose -f docker-compose-test.yml down

# Run
export MCP_SSH_CONFIG=/path/to/hosts.yaml
export MYHOST_PASS='...'
poetry run mcp-ssh                          # stdio transport (default)

# SSE transport
export MCP_TRANSPORT=sse
export MCP_AUTH_TOKEN=$(python -c "import secrets; print(secrets.token_hex(32))")
export MCP_PORT=8000    # optional, defaults to 8000
poetry run mcp-ssh      # MCP_HOST defaults to 127.0.0.1; set to 0.0.0.0 only behind a reverse proxy
```

## Architecture

The server is a [FastMCP](https://github.com/jlowin/fastmcp) application that exposes six tools over stdio or SSE. The call flow for a command is:

```
server._execute()
  → safety.classify_command()      # regex match against deny_patterns
  → audit.log()                    # append to audit log
  → SessionManager.get()           # create or reuse SSHConnection
      → SSHConnection.run_exec()   # posix, stateless (asyncssh exec)
      → SSHConnection.run_in_shell() → ShellSession.run()   # posix interactive or cli
```

**Key modules:**

- [mcp_ssh/server.py](mcp_ssh/server.py) — FastMCP tool definitions, `AppState` singleton, transport selection (`stdio` vs `sse`), bearer-auth middleware for SSE mode.
- [mcp_ssh/session_manager.py](mcp_ssh/session_manager.py) — pools `SSHConnection` objects by host name; reaps idle sessions on a 60-second background loop.
- [mcp_ssh/connection.py](mcp_ssh/connection.py) — wraps `asyncssh`. `run_exec` is stateless (one SSH exec per call); `run_in_shell` is stateful (persistent PTY via `ShellSession`).
- [mcp_ssh/shell_session.py](mcp_ssh/shell_session.py) — reads PTY output until a sentinel marker (posix) or prompt regex (cli) appears.
- [mcp_ssh/models.py](mcp_ssh/models.py) — Pydantic models: `AppConfig`, `HostConfig`, `Settings`, `CommandResult`, `BlockedResult`. `Settings` contains default `deny_patterns`.
- [mcp_ssh/config.py](mcp_ssh/config.py) — loads `hosts.yaml`, resolves `MCP_SSH_CONFIG` env var, validates env refs for secrets.
- [mcp_ssh/safety.py](mcp_ssh/safety.py) — regex-based danger classification; no side effects.
- [mcp_ssh/audit.py](mcp_ssh/audit.py) — append-only JSONL audit log.

## Shell types

`shell: posix` uses `run_exec` for `ssh_run` and a PTY with a sentinel marker for `ssh_shell`. `shell: cli` always uses the PTY path (`run_in_shell`) — `prompt_regex` is required to detect command completion.

## Configuration

`hosts.yaml` stores host topology only. Secrets (passwords, passphrases) are referenced by the **name** of an environment variable (`password_env`, `passphrase_env`); the actual values must be exported before the server starts. `load_config` raises `MissingEnvError` at startup if a referenced env var is absent.

`settings.deny_patterns` is a list of Python regexes matched against every command. A match blocks execution and returns a `BlockedResult` unless `confirm_dangerous=true` is passed.

## SSE / Portainer deployment

See [docs/portainer-deployment.md](docs/portainer-deployment.md). `MCP_TRANSPORT=sse` requires `MCP_AUTH_TOKEN`; the server enforces bearer auth via constant-time comparison. `MCP_HOST` defaults to `127.0.0.1`; set `0.0.0.0` only when a reverse proxy handles auth in front.

`docker-compose.yml` — продакшн-стек для Portainer / сервера.
`docker-compose-test.yml` — тестовый SSH-сервер (только для интеграционных тестов).
