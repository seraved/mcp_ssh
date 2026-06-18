import json

from mcp_ssh.audit import AuditLogger


def test_log_writes_jsonl(tmp_path):
    log_path = tmp_path / "sub" / "audit.log"
    logger = AuditLogger(str(log_path))
    logger.log(host="h1", tool="ssh_run", command="ls", decision="executed",
               exit_code=0)
    logger.log(host="h1", tool="ssh_shell", command="reboot",
               decision="blocked_pending_confirm")

    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["host"] == "h1"
    assert first["command"] == "ls"
    assert first["decision"] == "executed"
    assert first["exit_code"] == 0
    assert "ts" in first
    second = json.loads(lines[1])
    assert second["decision"] == "blocked_pending_confirm"
    assert second["exit_code"] is None
