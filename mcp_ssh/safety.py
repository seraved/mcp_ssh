from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import HostConfig, PolicyMode

# Tools that never bear a command string (no command to filter).
# Extend when new non-command tools are added.
READONLY_BLOCKED_TOOLS: frozenset[str] = frozenset()

COMMAND_BEARING_TOOLS: frozenset[str] = frozenset({"ssh_run", "ssh_shell"})

# Built-in denylist for readonly mode — adapted from mcp-ssh-manager v3.5.0.
# These are guardrails against accidental destructive commands, not a security boundary.
_READONLY_DENY_RAW: list[str] = [
    r"(^|[\s;&|])rm(\s|$)",
    r"(^|[\s;&|])rmdir(\s|$)",
    r"(^|[\s;&|])mv(\s|$)",
    r"(^|[\s;&|])dd(\s|$)",
    r"(^|[\s;&|])mkfs([.\s]|$)",
    r"(^|[\s;&|])chmod(\s|$)",
    r"(^|[\s;&|])chown(\s|$)",
    r"(^|[\s;&|])truncate(\s|$)",
    r"(^|[\s;&|])tee(\s|$)",
    r"(^|[\s;&|])sudo(\s|$)",
    r"(^|[\s;&|])su(\s|$)",
    r"(^|[\s;&|])kill(\s|$)",
    r"(^|[\s;&|])pkill(\s|$)",
    r"(^|[\s;&|])killall(\s|$)",
    r"(^|[\s;&|])shutdown(\s|$)",
    r"(^|[\s;&|])reboot(\s|$)",
    r"(^|[\s;&|])halt(\s|$)",
    r"(^|[\s;&|])poweroff(\s|$)",
    r"(^|[\s;&|])systemctl\s+(restart|stop|reload|start|enable|disable|mask)",
    r"(^|[\s;&|])service\s+\S+\s+(restart|stop|reload|start)",
    r"(^|[\s;&|])docker\s+(rm|stop|restart|kill|prune|system)",
    r"(^|[\s;&|])apt(-get)?\s+(install|remove|purge|upgrade|update)",
    r"(^|[\s;&|])yum\s+(install|remove|update|upgrade)",
    r"(^|[\s;&|])dnf\s+(install|remove|update|upgrade)",
    r"(^|[\s;&|])pip\s+(install|uninstall)",
    r"(^|[\s;&|])npm\s+(install|uninstall|publish)",
    r"(^|[\s;&|])git\s+(reset\s+--hard|push\s+.*--force|clean\s+-fd?)",
    r">\s*/(?!dev/null|dev/stdout|dev/stderr|tmp)",
    r">>\s*/(?!dev/null|tmp)",
    r"\|\s*sh(\s|$)",
    r"\|\s*bash(\s|$)",
    r"curl\s+[^|]*\|\s*(sh|bash)",
    r"wget\s+[^|]*\|\s*(sh|bash)",
]

_READONLY_DENY_RE: list[re.Pattern] = [re.compile(p) for p in _READONLY_DENY_RAW]

# Per-host compiled pattern cache: host_name -> (allow_src, deny_src, allow_re, deny_re)
_pattern_cache: dict[str, tuple[str, str, list[re.Pattern], list[re.Pattern]]] = {}


def _get_host_patterns(
    host_name: str, host_cfg: "HostConfig"
) -> tuple[list[re.Pattern], list[re.Pattern]]:
    allow_src = "|".join(host_cfg.allow_patterns)
    deny_src = "|".join(host_cfg.deny_patterns)
    cached = _pattern_cache.get(host_name)
    if cached and cached[0] == allow_src and cached[1] == deny_src:
        return cached[2], cached[3]

    allow_re: list[re.Pattern] = []
    for p in host_cfg.allow_patterns:
        try:
            allow_re.append(re.compile(p))
        except re.error:
            pass

    deny_re: list[re.Pattern] = []
    for p in host_cfg.deny_patterns:
        try:
            deny_re.append(re.compile(p))
        except re.error:
            pass

    _pattern_cache[host_name] = (allow_src, deny_src, allow_re, deny_re)
    return allow_re, deny_re


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str | None = None
    matched_pattern: str | None = None
    bypassable: bool = False  # True only in unrestricted mode (confirm_dangerous works)


@dataclass
class SafetyDecision:
    """Kept for backward compatibility with existing tests."""
    dangerous: bool
    matched_pattern: str | None = None


def classify_command(command: str, deny_patterns: list[str]) -> SafetyDecision:
    """Original API — still used by tests and external callers."""
    for pattern in deny_patterns:
        if re.search(pattern, command):
            return SafetyDecision(dangerous=True, matched_pattern=pattern)
    return SafetyDecision(dangerous=False, matched_pattern=None)


def evaluate_policy(
    host_name: str,
    host_cfg: "HostConfig | None",
    tool_name: str,
    command: str,
    global_deny_patterns: list[str],
) -> PolicyDecision:
    """Evaluate whether a tool call is permitted under the host's security mode.

    unrestricted — uses global deny_patterns; confirm_dangerous can bypass.
    readonly     — built-in + host deny_patterns applied; no bypass.
    restricted   — host allow_patterns + deny_patterns; fail-closed; no bypass.
    """
    from .models import PolicyMode

    mode = host_cfg.mode if host_cfg is not None else PolicyMode.unrestricted

    if mode == PolicyMode.unrestricted:
        for pattern in global_deny_patterns:
            if re.search(pattern, command):
                return PolicyDecision(
                    allowed=False,
                    reason=f"Command matches dangerous pattern: '{pattern}'",
                    matched_pattern=pattern,
                    bypassable=True,
                )
        return PolicyDecision(allowed=True)

    if mode == PolicyMode.readonly:
        if tool_name in READONLY_BLOCKED_TOOLS:
            return PolicyDecision(
                allowed=False,
                reason=f"Tool '{tool_name}' is blocked in readonly mode.",
            )
        if tool_name in COMMAND_BEARING_TOOLS:
            for compiled in _READONLY_DENY_RE:
                if compiled.search(command):
                    return PolicyDecision(
                        allowed=False,
                        reason=f"Command refused (readonly): matches built-in destructive pattern {compiled.pattern!r}.",
                        matched_pattern=compiled.pattern,
                    )
            if host_cfg is not None:
                _, deny_re = _get_host_patterns(host_name, host_cfg)
                for compiled in deny_re:
                    if compiled.search(command):
                        return PolicyDecision(
                            allowed=False,
                            reason=f"Command refused (readonly): matches host deny pattern {compiled.pattern!r}.",
                            matched_pattern=compiled.pattern,
                        )
        return PolicyDecision(allowed=True)

    if mode == PolicyMode.restricted:
        if tool_name not in COMMAND_BEARING_TOOLS:
            if tool_name in READONLY_BLOCKED_TOOLS:
                return PolicyDecision(
                    allowed=False,
                    reason=f"Tool '{tool_name}' is blocked in restricted mode.",
                )
            return PolicyDecision(allowed=True)

        allow_re, deny_re = _get_host_patterns(host_name, host_cfg) if host_cfg else ([], [])

        for compiled in deny_re:
            if compiled.search(command):
                return PolicyDecision(
                    allowed=False,
                    reason=f"Command refused (restricted): matches DENY pattern {compiled.pattern!r}.",
                    matched_pattern=compiled.pattern,
                )

        if not allow_re:
            return PolicyDecision(
                allowed=False,
                reason=f"Command refused (restricted): no allow_patterns configured — restricted mode requires an explicit allowlist.",
            )

        for compiled in allow_re:
            if compiled.search(command):
                return PolicyDecision(allowed=True)

        return PolicyDecision(
            allowed=False,
            reason="Command refused (restricted): does not match any allow_patterns.",
        )

    return PolicyDecision(
        allowed=False,
        reason=f"Unknown security mode '{mode}' on host '{host_name}'.",
    )
