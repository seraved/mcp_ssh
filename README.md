# mcp-ssh

MCP (stdio) server that lets an agent run commands over persistent SSH sessions
on multiple named hosts.

## Install

```bash
poetry config virtualenvs.in-project true --local
poetry install
```

## Configure hosts

Copy `hosts.example.yaml` to `hosts.yaml` and edit it. Point the server at it
with the `MCP_SSH_CONFIG` env var (defaults to `hosts.yaml` next to the package).

Secrets are **never** stored in the file — only the **name** of an environment
variable. Export the actual secret before launching:

```bash
export OPENWRT_PASS='...'
export CISCO_PASS='...'
export MCP_SSH_CONFIG=/path/to/hosts.yaml
```

### Choosing `shell`

`shell` describes the remote shell type, not the hardware:

| Device | `shell` | Why |
|---|---|---|
| Linux server, Raspberry Pi | `posix` | normal POSIX shell, has `echo $?` |
| OpenWRT / DD-WRT | `posix` | BusyBox `ash` is a POSIX shell |
| Cisco IOS | `cli` | custom CLI with modes, no `$?` |
| MikroTik RouterOS | `cli` | custom CLI |
| Managed switches | `cli` | custom CLI |

For `cli` hosts set `prompt_regex` to a regex matching the device prompt — it is
how command completion is detected.

## Tools

- `ssh_list_hosts` — list configured hosts.
- `ssh_connect(host_name)` — open/reuse a session.
- `ssh_run(host_name, command, confirm_dangerous=false)` — stateless command.
- `ssh_shell(host_name, command, confirm_dangerous=false)` — stateful command in
  a persistent interactive shell (keeps cwd, env, router config modes).
- `ssh_list_sessions` / `ssh_disconnect(host_name)`.

Commands matching `settings.deny_patterns` are blocked until re-called with
`confirm_dangerous=true`. Every attempt is written to the audit log.

## Connecting to an agent

Run over stdio:

```bash
poetry run mcp-ssh
```

Register the command `poetry run mcp-ssh` (with `MCP_SSH_CONFIG` and secret env
vars set) as a stdio MCP server in your agent.

## Development & tests

```bash
docker compose up -d                       # start the test SSH server
poetry run pytest -m "not integration"     # fast unit tests
poetry run pytest                          # full suite (needs the container)
docker compose down
```
