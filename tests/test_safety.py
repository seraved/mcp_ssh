from mcp_ssh.safety import classify_command


PATTERNS = [r"rm\s+-rf\s+/", r"\breboot\b", r"\bwrite\s+erase\b"]


def test_safe_command():
    d = classify_command("ls -la /etc", PATTERNS)
    assert d.dangerous is False
    assert d.matched_pattern is None


def test_dangerous_rm():
    d = classify_command("rm -rf /var/log", PATTERNS)
    assert d.dangerous is True
    assert d.matched_pattern == r"rm\s+-rf\s+/"


def test_dangerous_reboot_word_boundary():
    assert classify_command("reboot", PATTERNS).dangerous is True
    # 'rebooter' should NOT match because of the word boundary
    assert classify_command("rebooter --help", PATTERNS).dangerous is False


def test_cli_write_erase():
    d = classify_command("write erase", PATTERNS)
    assert d.dangerous is True
    assert d.matched_pattern == r"\bwrite\s+erase\b"
