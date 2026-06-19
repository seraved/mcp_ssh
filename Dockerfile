FROM python:3.12-slim

# Run as non-root
RUN useradd -r -u 1000 -s /sbin/nologin mcpssh

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt uvicorn starlette

COPY mcp_ssh/ ./mcp_ssh/
COPY pyproject.toml README.md ./

RUN pip install --no-cache-dir -e . --no-deps

# Directories for config, keys, audit log
RUN mkdir -p /config /keys /data && \
    echo 'hosts: {}' > /config/hosts.yaml && \
    chown -R mcpssh:mcpssh /config /data

USER mcpssh

# SSE mode — MCP_AUTH_TOKEN *must* be provided at runtime, server refuses to
# start without it. MCP_HOST defaults to 127.0.0.1; set to 0.0.0.0 only when
# a reverse proxy that enforces authentication sits in front.
ENV MCP_TRANSPORT=sse
ENV MCP_HOST=127.0.0.1
ENV MCP_PORT=8000
ENV MCP_SSH_CONFIG=/config/hosts.yaml

# Do NOT publish this port without a reverse proxy + auth in front.
EXPOSE 8000

CMD ["python", "-m", "mcp_ssh.server"]
