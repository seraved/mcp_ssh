from mcp_ssh.parsers import (
    make_marker, wrap_posix_command, parse_marker, prompt_matched,
    truncate_output,
)


def test_make_marker_unique():
    assert make_marker() != make_marker()


def test_wrap_posix_command():
    assert wrap_posix_command("ls", "MARK") == 'ls\necho "MARK:$?"'


def test_parse_marker_found():
    buf = "file1\nfile2\nMARK:0\n"
    out, code = parse_marker(buf, "MARK")
    assert out == "file1\nfile2\n"
    assert code == 0


def test_parse_marker_nonzero():
    buf = "oops\nMARK:127\n"
    out, code = parse_marker(buf, "MARK")
    assert out == "oops\n"
    assert code == 127


def test_parse_marker_absent():
    assert parse_marker("still running...\n", "MARK") is None


def test_prompt_matched():
    assert prompt_matched("switch1(config)#", r"[\w.()-]+[>#]\s*$") is True
    assert prompt_matched("still running", r"[\w.()-]+[>#]\s*$") is False


def test_truncate_output():
    text, truncated = truncate_output("abcdef", 3)
    assert truncated is True
    assert text.encode("utf-8")[:3] == b"abc"
    text2, truncated2 = truncate_output("abc", 10)
    assert truncated2 is False
    assert text2 == "abc"
