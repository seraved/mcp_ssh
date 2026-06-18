from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class AuditLogger:
    def __init__(self, log_path: str):
        self._path = Path(log_path).expanduser()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        *,
        host: str,
        tool: str,
        command: str,
        decision: str,
        exit_code: int | None = None,
        timed_out: bool = False,
    ) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "host": host,
            "tool": tool,
            "command": command,
            "decision": decision,
            "exit_code": exit_code,
            "timed_out": timed_out,
        }
        with open(self._path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
