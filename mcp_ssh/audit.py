from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_REDACT_RE = re.compile(
    r"(password|passwd|pass|passphrase|token|secret|api[_-]?key)(\s*[=:]\s*)\S+",
    re.IGNORECASE,
)

_warned_paths: set[str] = set()


def _redact(command: str) -> str:
    return _REDACT_RE.sub(r"\1\2***", command)


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
        reason: str | None = None,
    ) -> None:
        record: dict = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "host": host,
            "tool": tool,
            "command": _redact(command),
            "decision": decision,
            "exit_code": exit_code,
            "timed_out": timed_out,
        }
        if reason is not None:
            record["reason"] = reason
        path_str = str(self._path)
        try:
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            if path_str not in _warned_paths:
                _warned_paths.add(path_str)
                print(
                    f"[mcp-ssh] audit write failed for {path_str}: {exc} (further failures silenced)",
                    file=sys.stderr,
                    flush=True,
                )
