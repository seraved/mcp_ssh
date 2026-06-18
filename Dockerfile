FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY mcp_ssh/ ./mcp_ssh/
COPY pyproject.toml .

RUN pip install --no-cache-dir -e . --no-deps

ENV MCP_TRANSPORT=sse
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000
ENV MCP_SSH_CONFIG=/config/hosts.yaml

EXPOSE 8000

CMD ["python", "-m", "mcp_ssh.server"]
