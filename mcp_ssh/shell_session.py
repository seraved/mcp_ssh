from __future__ import annotations

import asyncio
import re
import time

from .models import CommandResult, ShellType
from .parsers import (
    make_marker, parse_marker, prompt_matched, truncate_output, wrap_posix_command,
)

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\r")


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text)


class ShellSession:
    def __init__(self, process, shell_type: ShellType, prompt_regex, max_output_bytes):
        self._proc = process
        self._shell_type = shell_type
        self._prompt_regex = prompt_regex
        self._max_output_bytes = max_output_bytes

    async def _drain(self) -> None:
        try:
            while True:
                await asyncio.wait_for(self._proc.stdout.read(65536), timeout=0.1)
        except asyncio.TimeoutError:
            return

    async def run(self, command: str, timeout: float) -> CommandResult:
        await self._drain()
        start = time.monotonic()

        if self._shell_type is ShellType.posix:
            marker = make_marker()
            self._proc.stdin.write(wrap_posix_command(command, marker) + "\n")
        else:
            marker = None
            self._proc.stdin.write(command + "\n")

        buffer = ""
        while True:
            remaining = timeout - (time.monotonic() - start)
            if remaining <= 0:
                text, truncated = truncate_output(buffer, self._max_output_bytes)
                return CommandResult(
                    output=text, duration=time.monotonic() - start,
                    timed_out=True, truncated=truncated,
                    hint=f"Command did not finish within {timeout}s. "
                         "Possibly awaiting input. Session kept open.",
                )
            try:
                chunk = await asyncio.wait_for(
                    self._proc.stdout.read(65536), timeout=remaining)
            except asyncio.TimeoutError:
                continue
            buffer += chunk

            if marker is not None:
                parsed = parse_marker(_strip_ansi(buffer), marker)
                if parsed is not None:
                    out, code = parsed
                    text, truncated = truncate_output(out, self._max_output_bytes)
                    return CommandResult(
                        output=text, exit_code=code,
                        duration=time.monotonic() - start, truncated=truncated)
            elif self._prompt_regex and prompt_matched(buffer, self._prompt_regex):
                text, truncated = truncate_output(buffer, self._max_output_bytes)
                return CommandResult(
                    output=text, exit_code=None,
                    duration=time.monotonic() - start, truncated=truncated)

    async def close(self) -> None:
        try:
            self._proc.stdin.write_eof()
        except OSError:
            pass
        self._proc.close()
