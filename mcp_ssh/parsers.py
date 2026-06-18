from __future__ import annotations

import re
import uuid


def make_marker() -> str:
    return f"__MCPSSH_{uuid.uuid4().hex}__"


def wrap_posix_command(command: str, marker: str) -> str:
    return f'{command}\necho "{marker}:$?"'


def parse_marker(buffer: str, marker: str) -> tuple[str, int] | None:
    match = re.search(rf"^{re.escape(marker)}:(\d+)\s*$", buffer, re.MULTILINE)
    if not match:
        return None
    before = buffer[: match.start()]
    return before, int(match.group(1))


def prompt_matched(buffer: str, prompt_regex: str) -> bool:
    return re.search(prompt_regex, buffer) is not None


def truncate_output(text: str, max_bytes: int) -> tuple[str, bool]:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text, False
    truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return truncated, True
