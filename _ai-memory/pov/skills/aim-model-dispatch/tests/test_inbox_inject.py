"""Companion test for scripts/lib/inbox_inject.sh.

Exercises the two modes (deliver / capture) and the capture→deliver
ordering constraint from the 7 inline forms in aim-model-dispatch step files:
  - 5 api-dispatch deliver forms (no guard, --from api-dispatch, --color green)
  - 2 bmad/tmux monitor-and-capture forms (if-file guard, --color purple/blue)

Harness: stdlib subprocess only — no pytest-shell-utilities (DEC-113).
Pattern: explicit minimal env on every call (BP-016 §9 anti-flake rule).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _make_env(home_dir: Path) -> dict[str, str]:
    """Minimal env: HOME controls ~/.claude/teams/ resolution; PATH + LC_ALL pinned."""
    return {
        "HOME": str(home_dir),
        "PATH": os.environ["PATH"],
        "LC_ALL": "C",
    }


def _inbox_path(home_dir: Path) -> Path:
    """Canonical inbox JSON path under the controlled HOME."""
    return home_dir / ".claude" / "teams" / "test-team" / "inboxes" / "team-lead.json"


def _run(
    helper: Path,
    *,
    inbox: Path,
    mode: str,
    sender: str = "test-agent",
    message: str | None = "hello",
    color: str = "blue",
    env: dict[str, str],
    tmp_path: Path,
    stdin_input: str | None = None,
) -> subprocess.CompletedProcess:
    """Run inbox_inject.sh with the given arguments."""
    cmd = [
        "bash",
        str(helper),
        "--inbox-path",
        str(inbox),
        "--mode",
        mode,
        "--from",
        sender,
        "--color",
        color,
    ]
    if message is not None:
        cmd += ["--message", message]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(tmp_path),
        env=env,
        input=stdin_input,
    )


# ---------------------------------------------------------------------------
# Session fixture (from conftest.py: scripts_dir)
# ---------------------------------------------------------------------------


@pytest.fixture
def helper(scripts_dir: Path) -> Path:
    p = scripts_dir / "inbox_inject.sh"
    assert p.exists(), f"Helper not found: {p}"
    return p


# ---------------------------------------------------------------------------
# deliver mode — creates and appends
# ---------------------------------------------------------------------------


def test_deliver_creates_inbox(helper: Path, tmp_path: Path) -> None:
    """deliver on an empty dir creates the inbox file with one message."""
    env = _make_env(tmp_path)
    inbox = _inbox_path(tmp_path)

    result = _run(
        helper,
        inbox=inbox,
        mode="deliver",
        message="hello-world",
        env=env,
        tmp_path=tmp_path,
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert inbox.exists()
    messages = json.loads(inbox.read_text())
    assert len(messages) == 1
    assert messages[0]["text"] == "hello-world"
    assert messages[0]["from"] == "test-agent"
    assert messages[0]["color"] == "blue"


def test_deliver_passes_color(helper: Path, tmp_path: Path) -> None:
    """--color is forwarded to inbox-inject.py and persisted in the JSON."""
    env = _make_env(tmp_path)
    inbox = _inbox_path(tmp_path)

    result = _run(
        helper,
        inbox=inbox,
        mode="deliver",
        message="msg",
        color="green",
        env=env,
        tmp_path=tmp_path,
    )

    assert result.returncode == 0
    messages = json.loads(inbox.read_text())
    assert messages[0]["color"] == "green"


def test_deliver_appends_second_message(helper: Path, tmp_path: Path) -> None:
    """Two consecutive deliver calls append both messages in order."""
    env = _make_env(tmp_path)
    inbox = _inbox_path(tmp_path)

    _run(
        helper, inbox=inbox, mode="deliver", message="first", env=env, tmp_path=tmp_path
    )
    _run(
        helper,
        inbox=inbox,
        mode="deliver",
        message="second",
        env=env,
        tmp_path=tmp_path,
    )

    messages = json.loads(inbox.read_text())
    assert len(messages) == 2
    assert messages[0]["text"] == "first"
    assert messages[1]["text"] == "second"


# ---------------------------------------------------------------------------
# capture mode — guard behaviour
# ---------------------------------------------------------------------------


def test_capture_noop_when_inbox_absent(helper: Path, tmp_path: Path) -> None:
    """capture on a non-existent inbox exits 0 and creates NO file (the guard)."""
    env = _make_env(tmp_path)
    inbox = _inbox_path(tmp_path)

    result = _run(
        helper,
        inbox=inbox,
        mode="capture",
        message="should-not-appear",
        env=env,
        tmp_path=tmp_path,
    )

    assert result.returncode == 0
    assert result.stdout == ""
    assert not inbox.exists()


def test_capture_appends_when_inbox_exists(helper: Path, tmp_path: Path) -> None:
    """capture on an existing inbox appends the message normally."""
    env = _make_env(tmp_path)
    inbox = _inbox_path(tmp_path)

    _run(
        helper, inbox=inbox, mode="deliver", message="seed", env=env, tmp_path=tmp_path
    )
    result = _run(
        helper,
        inbox=inbox,
        mode="capture",
        message="captured",
        env=env,
        tmp_path=tmp_path,
    )

    assert result.returncode == 0
    messages = json.loads(inbox.read_text())
    assert len(messages) == 2
    assert messages[0]["text"] == "seed"
    assert messages[1]["text"] == "captured"


# ---------------------------------------------------------------------------
# Ordering constraint: capture→deliver sequence (the HARD-RAIL caveat)
# ---------------------------------------------------------------------------


def test_ordering_capture_before_deliver_is_noop(helper: Path, tmp_path: Path) -> None:
    """Ordering constraint: capture BEFORE any deliver is a silent no-op.
    Only deliver(B) appears in the final inbox — A was swallowed by the guard."""
    env = _make_env(tmp_path)
    inbox = _inbox_path(tmp_path)

    # Step 1: capture on absent inbox — must be a silent no-op
    r1 = _run(
        helper, inbox=inbox, mode="capture", message="A", env=env, tmp_path=tmp_path
    )
    assert r1.returncode == 0
    assert not inbox.exists(), "capture must not create the inbox"

    # Step 2: deliver creates inbox with message B
    r2 = _run(
        helper, inbox=inbox, mode="deliver", message="B", env=env, tmp_path=tmp_path
    )
    assert r2.returncode == 0

    messages = json.loads(inbox.read_text())
    assert len(messages) == 1
    assert messages[0]["text"] == "B"


def test_ordering_deliver_then_capture_sequence(helper: Path, tmp_path: Path) -> None:
    """Standard sequence: deliver(A) → capture(B) → inbox holds [A, B] in order."""
    env = _make_env(tmp_path)
    inbox = _inbox_path(tmp_path)

    r1 = _run(
        helper, inbox=inbox, mode="deliver", message="A", env=env, tmp_path=tmp_path
    )
    assert r1.returncode == 0

    r2 = _run(
        helper, inbox=inbox, mode="capture", message="B", env=env, tmp_path=tmp_path
    )
    assert r2.returncode == 0

    messages = json.loads(inbox.read_text())
    assert len(messages) == 2
    assert messages[0]["text"] == "A"
    assert messages[1]["text"] == "B"


# ---------------------------------------------------------------------------
# stdin message source
# ---------------------------------------------------------------------------


def test_stdin_message(helper: Path, tmp_path: Path) -> None:
    """--message omitted: message text is read from stdin."""
    env = _make_env(tmp_path)
    inbox = _inbox_path(tmp_path)

    cmd = [
        "bash",
        str(helper),
        "--inbox-path",
        str(inbox),
        "--mode",
        "deliver",
        "--from",
        "stdin-sender",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(tmp_path),
        env=env,
        input="from-stdin-content",
    )

    assert result.returncode == 0
    messages = json.loads(inbox.read_text())
    assert messages[0]["text"] == "from-stdin-content"
    assert messages[0]["from"] == "stdin-sender"


# ---------------------------------------------------------------------------
# Error cases — parametrized (BP-016 §11)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "extra_args,description",
    [
        ([], "missing all required args"),
        (["--mode", "deliver", "--from", "x"], "missing --inbox-path"),
        (["--inbox-path", "dummy.json", "--from", "x"], "missing --mode"),
        (["--inbox-path", "dummy.json", "--mode", "deliver"], "missing --from"),
        (
            ["--inbox-path", "dummy.json", "--mode", "invalid", "--from", "x"],
            "invalid mode value",
        ),
        (
            [
                "--inbox-path",
                "dummy.json",
                "--mode",
                "deliver",
                "--from",
                "x",
                "--unknown",
                "y",
            ],
            "unknown argument",
        ),
    ],
)
def test_error_cases(
    helper: Path,
    tmp_path: Path,
    extra_args: list[str],
    description: str,
) -> None:
    """Missing required args or invalid mode → non-zero exit, stderr non-empty, stdout empty."""
    env = _make_env(tmp_path)
    result = subprocess.run(
        ["bash", str(helper), *extra_args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(tmp_path),
        env=env,
        input="",
    )

    assert result.returncode != 0, f"Expected non-zero for: {description}"
    assert result.stdout == "", f"Stdout must be empty on error: {description}"
    assert result.stderr != "", f"Stderr must describe the error: {description}"
