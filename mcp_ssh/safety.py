from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SafetyDecision:
    dangerous: bool
    matched_pattern: str | None = None


def classify_command(command: str, deny_patterns: list[str]) -> SafetyDecision:
    for pattern in deny_patterns:
        if re.search(pattern, command):
            return SafetyDecision(dangerous=True, matched_pattern=pattern)
    return SafetyDecision(dangerous=False, matched_pattern=None)
