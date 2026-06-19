# Развёртывание mcp-ssh на Portainer

## Архитектура

```
Агент (Claude / Cursor)
    │  HTTP + Bearer token
    ▼
[nginx] (опционально, SSL + внешний доступ)
    │
    ▼
[mcp-ssh контейнер] — SSE-транспорт, порт 8000
    │  SSH
    ▼
Роутеры / серверы / сетевое оборудование
```

---

## Шаг 1: Сгенерируй токен аутентификации

```bash
python -c "import secrets; print(secrets.token_hex(32))"
# Пример: a3f8c2d1e4b7a9f0c6b3d2e1f4a7b8c9...
```

Сохрани токен — он нужен и серверу, и агенту.

> Без `MCP_AUTH_TOKEN` сервер **не запустится** в SSE-режиме — это намеренно.

---

## Шаг 2: Первый запуск — наполни конфиг хостов

`hosts.yaml` уже встроен в образ с пустой секцией `hosts: {}`. Сервер стартует сразу — без ручного создания файлов.

После деплоя стека зайди в консоль контейнера в Portainer:

**Containers → mcp-ssh → Console → `/bin/sh` → Connect**

Затем запусти интерактивный скрипт:

```bash
python manage_hosts.py
```

Скрипт предоставляет меню: список хостов, добавление, редактирование, удаление с подтверждением. Файл сохраняется в том `config` и переживает рестарты.

**После добавления хостов перезапусти контейнер** (Portainer → Containers → mcp-ssh → Restart) — сервер перечитывает конфиг при старте.

Если предпочитаешь редактировать YAML вручную — ориентируйся на `hosts.example.yaml` в репозитории:

```yaml
hosts:
  my-router:
    host: 192.168.1.1
    user: admin
    auth:
      method: password
      password_env: ROUTER_PASS   # имя переменной окружения, не сам пароль
    shell: posix

  my-server:
    host: 192.168.1.10
    user: ubuntu
    auth:
      method: key
      key_path: /keys/id_ed25519  # путь внутри контейнера
    shell: posix

  cisco-switch:
    host: 192.168.1.2
    user: cisco
    auth:
      method: password
      password_env: CISCO_PASS
    shell: cli
    prompt_regex: '[\w.()-]+[>#]\s*$'

settings:
  idle_timeout: 600
  command_timeout: 60
  audit_log: /data/audit.log
```

**Выбор `shell`:**

| Устройство | `shell` | Почему |
|---|---|---|
| Linux-сервер, Raspberry Pi | `posix` | Стандартный POSIX shell |
| OpenWRT / DD-WRT | `posix` | BusyBox `ash` — тоже POSIX |
| Cisco IOS / NX-OS | `cli` | Проприетарный CLI без `$?` |
| MikroTik RouterOS | `cli` | Проприетарный CLI |
| Управляемые коммутаторы | `cli` | Проприетарный CLI |

---

## Шаг 3: Собери Docker-образ

```bash
git clone <репозиторий> /opt/mcp-ssh
cd /opt/mcp-ssh
docker build -t mcp-ssh:latest .
```

Или в Portainer: **Images → Build image → Upload** (загрузи папку проекта).

---

## Шаг 4: Стек в Portainer

**Stacks → Add stack**, вставь:

```yaml
version: "3.8"

services:
  mcp-ssh:
    image: mcp-ssh:latest
    container_name: mcp-ssh
    restart: unless-stopped
    ports:
      - "127.0.0.1:8000:8000"   # только loopback хоста
    volumes:
      - config:/config                    # hosts.yaml (именованный том)
      - /opt/mcp-ssh/keys:/keys:ro        # SSH-ключи (если используешь key auth)
      - /opt/mcp-ssh/data:/data           # audit.log
    environment:
      MCP_TRANSPORT: sse
      MCP_HOST: "0.0.0.0"                 # внутри контейнера — снаружи только через порт выше
      MCP_PORT: "8000"
      MCP_AUTH_TOKEN: "a3f8c2d1e4b7a9f0..." # токен из шага 1
      MCP_SSH_CONFIG: /config/hosts.yaml
      # Пароли для SSH-хостов (имена берутся из password_env в hosts.yaml):
      ROUTER_PASS: "пароль_роутера"
      CISCO_PASS: "пароль_коммутатора"

volumes:
  config:
```

> **Секреты лучше хранить в Portainer Secrets**, а не прямо в стеке.

---

## Шаг 5 (опционально): nginx для доступа извне

Если агент находится на другой машине — поставь nginx перед контейнером:

```yaml
  nginx:
    image: nginx:alpine
    ports:
      - "8443:443"
    volumes:
      - /opt/mcp-ssh/nginx.conf:/etc/nginx/conf.d/mcp.conf:ro
      - /opt/mcp-ssh/certs:/etc/ssl/certs:ro
    depends_on:
      - mcp-ssh
```

Минимальный `nginx.conf`:

```nginx
server {
    listen 443 ssl;
    ssl_certificate     /etc/ssl/certs/fullchain.pem;
    ssl_certificate_key /etc/ssl/certs/privkey.pem;

    location / {
        proxy_pass http://mcp-ssh:8000;
        proxy_set_header Host $host;
        proxy_buffering off;          # важно для SSE
    }
}
```

---

## Шаг 6: Подключи агента

### Claude Desktop

`~/.config/claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mcp-ssh": {
      "type": "sse",
      "url": "http://192.168.1.100:8000/sse",
      "headers": {
        "Authorization": "Bearer a3f8c2d1e4b7a9f0..."
      }
    }
  }
}
```

### Cursor / Continue

`.cursor/mcp.json` (или аналог):

```json
{
  "servers": {
    "mcp-ssh": {
      "type": "sse",
      "url": "http://192.168.1.100:8000/sse",
      "headers": {
        "Authorization": "Bearer a3f8c2d1e4b7a9f0..."
      }
    }
  }
}
```

### Claude Code

`.claude/settings.json` проекта:

```json
{
  "mcpServers": {
    "mcp-ssh": {
      "type": "sse",
      "url": "http://192.168.1.100:8000/sse",
      "headers": {
        "Authorization": "Bearer a3f8c2d1e4b7a9f0..."
      }
    }
  }
}
```

---

## Шаг 7: Проверка

```bash
# Без токена — должен вернуть 401 Unauthorized:
curl http://192.168.1.100:8000/

# С токеном — должен ответить:
curl -H "Authorization: Bearer a3f8c2d1e4b7a9f0..." http://192.168.1.100:8000/

# Логи контейнера в Portainer:
# Containers → mcp-ssh → Logs
```

---

## Доступные инструменты

После подключения агент видит 6 инструментов:

| Инструмент | Параметры | Что делает |
|---|---|---|
| `ssh_list_hosts` | — | Список настроенных хостов (без паролей) |
| `ssh_connect` | `host_name` | Открыть / переиспользовать сессию |
| `ssh_run` | `host_name`, `command`, `confirm_dangerous?` | Одиночная команда (exec) |
| `ssh_shell` | `host_name`, `command`, `confirm_dangerous?` | Команда в постоянном shell (сохраняет cd, переменные, режимы CLI) |
| `ssh_list_sessions` | — | Активные сессии и время простоя |
| `ssh_disconnect` | `host_name` | Закрыть сессию |

**Опасные команды** (`rm -rf /`, `reboot`, `mkfs` и др.) блокируются автоматически.
Агент должен явно передать `confirm_dangerous=true` чтобы выполнить их.

---

## Безопасность

| Мера | Реализация |
|---|---|
| Аутентификация | Bearer-токен, constant-time сравнение (`hmac.compare_digest`) |
| Привязка порта | `127.0.0.1:8000` — только loopback хоста |
| Непривилегированный процесс | uid 1000 (`mcpssh`) внутри контейнера |
| Секреты в конфиге | Только имена переменных, сами значения — через env |
| Аудит | Все команды пишутся в `/data/audit.log` (JSONL) |
| Deny-list | 7 паттернов опасных команд, фильтрация на сервере |
| Fail-closed | Сервер не стартует в SSE-режиме без `MCP_AUTH_TOKEN` |
