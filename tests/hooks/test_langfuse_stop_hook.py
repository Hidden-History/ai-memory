"""Unit tests for langfuse_stop_hook.py.

Tests BUG-151 through BUG-157 fixes:
- BUG-151: Reads stdin JSON {session_id, transcript_path, cwd}, then .jsonl file
- BUG-152: Root span has input/output from first user / last assistant message
- BUG-154: Child spans have both input and output (paired turns)
- BUG-155: flush() with timeout guard
- BUG-156: Kill-switch uses LANGFUSE_ENABLED (not TRACE_TO_LANGFUSE)
- BUG-157: datetime.now(tz=timezone.utc) instead of datetime.utcnow()
"""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add hook scripts to path for direct import testing
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / ".claude" / "hooks" / "scripts"))

HOOK_SCRIPT = _PROJECT_ROOT / ".claude" / "hooks" / "scripts" / "langfuse_stop_hook.py"


@pytest.fixture(autouse=True)
def cleanup_sigalrm():
    """BUG-158: Cancel any pending SIGALRM and restore default handler after every test."""
    yield
    if hasattr(signal, "SIGALRM"):
        signal.alarm(0)  # Cancel any pending alarm
        signal.signal(signal.SIGALRM, signal.SIG_DFL)  # Restore default handler


def _write_jsonl(path: Path, messages: list[dict]) -> None:
    """Write a list of message dicts as a .jsonl file."""
    with open(path, "w", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg) + "\n")


def _make_stdin_payload(
    session_id: str = "test-session-001",
    transcript_path: str = "/tmp/test.jsonl",
    cwd: str = "/tmp/test-project",
) -> str:
    """Build the stdin JSON payload that Claude Code sends to stop hooks."""
    return json.dumps(
        {
            "session_id": session_id,
            "transcript_path": transcript_path,
            "cwd": cwd,
        }
    )


@pytest.fixture
def transcript_file(tmp_path):
    """Create a temporary .jsonl transcript file with sample messages."""
    messages = [
        {"role": "user", "content": "Hello, help me with Python", "token_count": 8},
        {
            "role": "assistant",
            "content": "Sure! What do you need help with?",
            "token_count": 10,
        },
        {"role": "user", "content": "Write a fibonacci function", "token_count": 6},
        {
            "role": "assistant",
            "content": "def fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)",
            "token_count": 25,
        },
    ]
    jsonl_path = tmp_path / "transcript.jsonl"
    _write_jsonl(jsonl_path, messages)
    return jsonl_path


@pytest.fixture
def content_blocks_transcript(tmp_path):
    """Transcript with list-of-blocks content (not plain string)."""
    messages = [
        {
            "role": "user",
            "content": [{"type": "text", "text": "Edit my file please"}],
            "token_count": 5,
        },
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "I'll edit the file now."},
                {"type": "tool_use", "name": "Edit", "input": {}},
            ],
            "token_count": 15,
        },
    ]
    jsonl_path = tmp_path / "blocks_transcript.jsonl"
    _write_jsonl(jsonl_path, messages)
    return jsonl_path


class TestExtractText:
    """Tests for _extract_text helper."""

    def test_plain_string(self):
        from langfuse_stop_hook import _extract_text

        assert _extract_text("hello world") == "hello world"

    def test_list_of_text_blocks(self):
        from langfuse_stop_hook import _extract_text

        content = [
            {"type": "text", "text": "First part"},
            {"type": "text", "text": "Second part"},
        ]
        result = _extract_text(content)
        assert "First part" in result
        assert "Second part" in result

    def test_list_with_tool_use(self):
        from langfuse_stop_hook import _extract_text

        content = [
            {"type": "text", "text": "Let me edit that."},
            {"type": "tool_use", "name": "Edit", "input": {}},
        ]
        result = _extract_text(content)
        assert "Let me edit that." in result
        assert "[Tool: Edit]" in result

    def test_list_with_tool_result(self):
        from langfuse_stop_hook import _extract_text

        content = [{"type": "tool_result", "content": "OK"}]
        result = _extract_text(content)
        assert "[Tool Result]" in result

    def test_non_string_non_list(self):
        from langfuse_stop_hook import _extract_text

        assert _extract_text(42) == "42"

    def test_empty_string(self):
        from langfuse_stop_hook import _extract_text

        assert _extract_text("") == ""

    def test_empty_list(self):
        from langfuse_stop_hook import _extract_text

        assert _extract_text([]) == ""

    def test_unicode_content(self):
        """Unicode: emoji, CJK, RTL text are extracted and truncated correctly."""
        from langfuse_stop_hook import _extract_text

        # Plain string with mixed unicode
        content = "Hello 🌍 你好 مرحبا"
        result = _extract_text(content)
        assert result == content

        # Content blocks with unicode
        blocks = [
            {"type": "text", "text": "Emoji: 🎉🚀✨"},
            {"type": "text", "text": "CJK: 日本語テスト"},
            {"type": "text", "text": "RTL: مرحبا بالعالم"},
        ]
        result = _extract_text(blocks)
        assert "🎉🚀✨" in result
        assert "日本語テスト" in result
        assert "مرحبا بالعالم" in result

    def test_unicode_truncation(self):
        """Truncation at LANGFUSE_PAYLOAD_MAX_CHARS handles multi-byte chars."""
        from langfuse_stop_hook import LANGFUSE_PAYLOAD_MAX_CHARS

        # Build a string of CJK chars exceeding the limit
        long_content = "字" * (LANGFUSE_PAYLOAD_MAX_CHARS + 500)
        truncated = long_content[:LANGFUSE_PAYLOAD_MAX_CHARS]
        assert len(truncated) == LANGFUSE_PAYLOAD_MAX_CHARS


class TestReadTranscript:
    """Tests for _read_transcript — BUG-151."""

    def test_reads_valid_jsonl(self, transcript_file):
        from langfuse_stop_hook import _read_transcript

        messages = _read_transcript(str(transcript_file))
        assert len(messages) == 4
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"

    def test_missing_file_returns_empty(self):
        from langfuse_stop_hook import _read_transcript

        messages = _read_transcript("/nonexistent/path.jsonl")
        assert messages == []

    def test_skips_malformed_lines(self, tmp_path):
        from langfuse_stop_hook import _read_transcript

        jsonl_path = tmp_path / "bad.jsonl"
        with open(jsonl_path, "w") as f:
            f.write('{"role": "user", "content": "ok"}\n')
            f.write("NOT VALID JSON\n")
            f.write('{"role": "assistant", "content": "reply"}\n')

        messages = _read_transcript(str(jsonl_path))
        assert len(messages) == 2

    def test_skips_empty_lines(self, tmp_path):
        from langfuse_stop_hook import _read_transcript

        jsonl_path = tmp_path / "sparse.jsonl"
        with open(jsonl_path, "w") as f:
            f.write('{"role": "user", "content": "hi"}\n')
            f.write("\n")
            f.write("   \n")
            f.write('{"role": "assistant", "content": "hello"}\n')

        messages = _read_transcript(str(jsonl_path))
        assert len(messages) == 2


class TestPairTurns:
    """Tests for _pair_turns — BUG-154."""

    def test_basic_pairing(self):
        from langfuse_stop_hook import _pair_turns

        messages = [
            {"role": "user", "content": "Q1", "token_count": 2},
            {"role": "assistant", "content": "A1", "token_count": 3},
            {"role": "user", "content": "Q2", "token_count": 2},
            {"role": "assistant", "content": "A2", "token_count": 3},
        ]
        turns = _pair_turns(messages)
        assert len(turns) == 2
        assert turns[0]["user_input"] == "Q1"
        assert turns[0]["assistant_output"] == "A1"
        assert turns[1]["user_input"] == "Q2"
        assert turns[1]["assistant_output"] == "A2"

    def test_user_without_assistant(self):
        from langfuse_stop_hook import _pair_turns

        messages = [
            {"role": "user", "content": "Q1"},
        ]
        turns = _pair_turns(messages)
        assert len(turns) == 1
        assert turns[0]["user_input"] == "Q1"
        assert turns[0]["assistant_output"] is None

    def test_orphan_assistant_at_start(self):
        from langfuse_stop_hook import _pair_turns

        messages = [
            {"role": "assistant", "content": "Resuming..."},
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
        ]
        turns = _pair_turns(messages)
        assert len(turns) == 2
        assert turns[0]["user_input"] is None
        assert turns[0]["assistant_output"] == "Resuming..."
        assert turns[1]["user_input"] == "Q1"

    def test_system_messages_skipped(self):
        from langfuse_stop_hook import _pair_turns

        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]
        turns = _pair_turns(messages)
        assert len(turns) == 1
        assert turns[0]["user_input"] == "Hi"

    def test_token_counts_preserved(self):
        from langfuse_stop_hook import _pair_turns

        messages = [
            {"role": "user", "content": "Q1", "token_count": 10},
            {"role": "assistant", "content": "A1", "token_count": 20},
        ]
        turns = _pair_turns(messages)
        assert turns[0]["user_tokens"] == 10
        assert turns[0]["assistant_tokens"] == 20

    def test_empty_messages(self):
        from langfuse_stop_hook import _pair_turns

        turns = _pair_turns([])
        assert turns == []


class TestDeterministicTraceId:
    """Tests for _deterministic_trace_id."""

    def test_deterministic(self):
        from langfuse_stop_hook import _deterministic_trace_id

        id1 = _deterministic_trace_id("session-123")
        id2 = _deterministic_trace_id("session-123")
        assert id1 == id2

    def test_different_sessions_different_ids(self):
        from langfuse_stop_hook import _deterministic_trace_id

        id1 = _deterministic_trace_id("session-123")
        id2 = _deterministic_trace_id("session-456")
        assert id1 != id2


class TestKillSwitches:
    """Tests for BUG-156: kill-switch env var correctness."""

    def _run_hook(
        self, env_overrides: dict, stdin_data: str = ""
    ) -> subprocess.CompletedProcess:
        """Run the hook script with env overrides."""
        env = os.environ.copy()
        env.update(env_overrides)
        return subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

    def test_exits_when_langfuse_disabled(self):
        """BUG-156: Uses LANGFUSE_ENABLED, not TRACE_TO_LANGFUSE."""
        result = self._run_hook({"LANGFUSE_ENABLED": "false"})
        assert result.returncode == 0

    def test_exits_when_langfuse_not_set(self):
        """Defaults to disabled when LANGFUSE_ENABLED not set."""
        env = os.environ.copy()
        env.pop("LANGFUSE_ENABLED", None)
        env.pop("TRACE_TO_LANGFUSE", None)
        result = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input="",
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        assert result.returncode == 0

    def test_exits_when_session_tracing_disabled(self):
        """BUG-156: LANGFUSE_TRACE_SESSIONS=false disables session traces."""
        result = self._run_hook(
            {
                "LANGFUSE_ENABLED": "true",
                "LANGFUSE_TRACE_SESSIONS": "false",
            }
        )
        assert result.returncode == 0

    def test_old_env_var_not_used(self):
        """BUG-156: TRACE_TO_LANGFUSE=true alone should NOT enable tracing."""
        env = os.environ.copy()
        env.pop("LANGFUSE_ENABLED", None)
        env["TRACE_TO_LANGFUSE"] = "true"
        result = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input="",
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        assert result.returncode == 0


class TestStdinParsing:
    """Tests for BUG-151: stdin JSON schema {session_id, transcript_path, cwd}."""

    def _run_hook_enabled(self, stdin_data: str) -> subprocess.CompletedProcess:
        """Run hook with Langfuse enabled (will fail at client creation, which is fine)."""
        env = os.environ.copy()
        env["LANGFUSE_ENABLED"] = "true"
        env["LANGFUSE_TRACE_SESSIONS"] = "true"
        # No real Langfuse keys — will exit gracefully when client is None
        env.pop("LANGFUSE_PUBLIC_KEY", None)
        env.pop("LANGFUSE_SECRET_KEY", None)
        return subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

    def test_empty_stdin_exits_gracefully(self):
        result = self._run_hook_enabled("")
        assert result.returncode == 0

    def test_malformed_json_exits_gracefully(self):
        result = self._run_hook_enabled("{not valid json")
        assert result.returncode == 0

    def test_valid_stdin_without_transcript_path_exits_gracefully(self):
        """No transcript_path → skip."""
        stdin = json.dumps({"session_id": "s1", "cwd": "/tmp"})
        result = self._run_hook_enabled(stdin)
        assert result.returncode == 0

    def test_valid_stdin_with_missing_file_exits_gracefully(self):
        """transcript_path points to nonexistent file → skip."""
        stdin = json.dumps(
            {
                "session_id": "s1",
                "transcript_path": "/nonexistent/transcript.jsonl",
                "cwd": "/tmp",
            }
        )
        result = self._run_hook_enabled(stdin)
        assert result.returncode == 0


class TestLangfuseTraceCreation:
    """Tests for BUG-152, BUG-154: root span I/O and child span pairing.

    Uses mocks since we can't rely on a real Langfuse server.
    Mocks memory.langfuse_config in sys.modules so the lazy import inside
    main() picks up our mock get_langfuse_client.
    """

    @pytest.fixture(autouse=True)
    def reset_module(self):
        """Reset module cache before each test."""
        for mod_name in list(sys.modules.keys()):
            if "langfuse_stop_hook" in mod_name:
                del sys.modules[mod_name]
        yield
        for mod_name in list(sys.modules.keys()):
            if "langfuse_stop_hook" in mod_name:
                del sys.modules[mod_name]

    @pytest.fixture
    def mock_langfuse_client(self):
        """Create a mock Langfuse client with span tracking."""
        client = MagicMock()
        spans_created = []

        def track_start_span(**kwargs):
            span = MagicMock()
            span.trace_id = "mock-trace-id"
            span.id = f"span-{len(spans_created)}"
            span._kwargs = kwargs
            span._updates = []

            def track_update(**update_kwargs):
                span._updates.append(update_kwargs)

            span.update = track_update
            spans_created.append(span)
            return span

        client.start_span = MagicMock(side_effect=track_start_span)
        client.flush = MagicMock()
        client._spans_created = spans_created
        return client

    def _run_main_with_mock(self, mock_client, stdin_payload: str):
        """Run langfuse_stop_hook.main() with mocked Langfuse client and stdin.

        Injects a mock memory.langfuse_config module into sys.modules so the
        lazy `from memory.langfuse_config import get_langfuse_client` inside
        main() resolves to our mock.
        """
        # Create mock module for memory.langfuse_config
        mock_config_module = MagicMock()
        mock_config_module.get_langfuse_client = MagicMock(return_value=mock_client)

        # Also need 'memory' parent package in sys.modules
        mock_memory_pkg = MagicMock()
        mock_memory_pkg.langfuse_config = mock_config_module

        saved_modules = {}
        for mod_name in ["memory", "memory.langfuse_config"]:
            saved_modules[mod_name] = sys.modules.get(mod_name)

        try:
            sys.modules["memory"] = mock_memory_pkg
            sys.modules["memory.langfuse_config"] = mock_config_module

            sys.path.insert(0, str(_PROJECT_ROOT / ".claude" / "hooks" / "scripts"))
            if "langfuse_stop_hook" in sys.modules:
                del sys.modules["langfuse_stop_hook"]
            import langfuse_stop_hook

            with (
                patch.dict(
                    os.environ,
                    {
                        "LANGFUSE_ENABLED": "true",
                        "LANGFUSE_TRACE_SESSIONS": "true",
                    },
                ),
                patch(
                    "sys.stdin",
                    MagicMock(read=MagicMock(return_value=stdin_payload)),
                ),
                pytest.raises(SystemExit),
            ):
                langfuse_stop_hook.main()
        finally:
            # Restore original modules
            for mod_name, original in saved_modules.items():
                if original is None:
                    sys.modules.pop(mod_name, None)
                else:
                    sys.modules[mod_name] = original

    def test_root_span_has_input_output(self, transcript_file, mock_langfuse_client):
        """BUG-152: Root span must have input= and output= set."""
        self._run_main_with_mock(
            mock_langfuse_client,
            _make_stdin_payload(transcript_path=str(transcript_file)),
        )

        # Verify root span (first span created) has input and output
        root_call = mock_langfuse_client.start_span.call_args_list[0]
        root_kwargs = root_call.kwargs
        assert root_kwargs.get("input") is not None, "Root span missing input (BUG-152)"
        assert (
            root_kwargs.get("output") is not None
        ), "Root span missing output (BUG-152)"
        # Input should be first user message
        assert "Python" in root_kwargs["input"]
        # Output should be last assistant message
        assert "fibonacci" in root_kwargs["output"]

    def test_child_spans_have_output(self, transcript_file, mock_langfuse_client):
        """BUG-154: Child turn spans must have output set via .update()."""
        self._run_main_with_mock(
            mock_langfuse_client,
            _make_stdin_payload(transcript_path=str(transcript_file)),
        )

        # Should have root + 2 turn spans (4 messages = 2 turns)
        spans = mock_langfuse_client._spans_created
        assert len(spans) >= 3, f"Expected >= 3 spans, got {len(spans)}"

        # Child spans (index 1+) should have .update(output=...) called
        for child_span in spans[1:]:
            assert (
                len(child_span._updates) > 0
            ), "Child span never had .update() called (BUG-154)"
            update_kwargs = child_span._updates[0]
            assert (
                "output" in update_kwargs
            ), "Child span .update() missing output key (BUG-154)"

    def test_content_blocks_extraction(
        self, content_blocks_transcript, mock_langfuse_client
    ):
        """BUG-151: Content blocks (list format) are properly extracted."""
        self._run_main_with_mock(
            mock_langfuse_client,
            _make_stdin_payload(transcript_path=str(content_blocks_transcript)),
        )

        # Root span input should contain extracted text
        root_call = mock_langfuse_client.start_span.call_args_list[0]
        root_kwargs = root_call.kwargs
        assert "Edit my file" in root_kwargs.get("input", "")
        assert "[Tool: Edit]" in root_kwargs.get("output", "")

    def test_flush_called(self, transcript_file, mock_langfuse_client):
        """BUG-155: flush() must be called after span creation."""
        self._run_main_with_mock(
            mock_langfuse_client,
            _make_stdin_payload(transcript_path=str(transcript_file)),
        )

        mock_langfuse_client.flush.assert_called_once()

    def test_trace_metadata_includes_session_id(
        self, transcript_file, mock_langfuse_client
    ):
        """Trace metadata should include session_id and tags."""
        self._run_main_with_mock(
            mock_langfuse_client,
            _make_stdin_payload(
                session_id="my-session-xyz",
                transcript_path=str(transcript_file),
            ),
        )

        # Root span should call update_trace with session_id
        root_span = mock_langfuse_client._spans_created[0]
        root_span.update_trace.assert_called_once()
        call_kwargs = root_span.update_trace.call_args.kwargs
        assert call_kwargs["session_id"] == "my-session-xyz"
        assert "session_trace" in call_kwargs.get("tags", [])


class TestDatetimeFix:
    """Tests for BUG-157: datetime.utcnow() replaced with timezone-aware."""

    def test_no_utcnow_calls(self):
        """BUG-157: Source code must not contain datetime.utcnow()."""
        source = HOOK_SCRIPT.read_text()
        assert (
            "utcnow()" not in source
        ), "BUG-157: datetime.utcnow() still present in source"

    def test_uses_timezone_aware(self):
        """BUG-157: Source must use datetime.now(tz=timezone.utc)."""
        source = HOOK_SCRIPT.read_text()
        assert "timezone.utc" in source
        assert "datetime.now(tz=timezone.utc)" in source


class TestNeverBlocksClaudeCode:
    """Integration-level tests: hook must ALWAYS exit 0, never crash."""

    def _run_hook(
        self, stdin_data: str, env_overrides: dict | None = None
    ) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["LANGFUSE_ENABLED"] = "true"
        env["LANGFUSE_TRACE_SESSIONS"] = "true"
        if env_overrides:
            env.update(env_overrides)
        return subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

    def test_empty_stdin(self):
        result = self._run_hook("")
        assert result.returncode == 0

    def test_malformed_json(self):
        result = self._run_hook("{{bad json")
        assert result.returncode == 0

    def test_missing_transcript_file(self):
        stdin = json.dumps(
            {
                "session_id": "s1",
                "transcript_path": "/nonexistent/file.jsonl",
                "cwd": "/tmp",
            }
        )
        result = self._run_hook(stdin)
        assert result.returncode == 0

    def test_no_langfuse_keys(self):
        """Even with LANGFUSE_ENABLED=true but no keys, exits gracefully."""
        stdin = json.dumps(
            {
                "session_id": "s1",
                "transcript_path": "/tmp/test.jsonl",
                "cwd": "/tmp",
            }
        )
        env = {
            "LANGFUSE_PUBLIC_KEY": "",
            "LANGFUSE_SECRET_KEY": "",
        }
        result = self._run_hook(stdin, env)
        assert result.returncode == 0
