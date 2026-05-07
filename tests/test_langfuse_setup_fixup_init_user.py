"""
Regression tests for TD-512: langfuse_setup.sh _fixup_init_user postgres role/db concatenation fix.

Verifies that the `_fixup_init_user` function body uses literal `langfuse` (not
`"$prefix"langfuse`) for psql -U and -d arguments, and that out-of-scope container
name construction is preserved unchanged.

Tests operate on the script source text — no bash execution required.
"""

import re
import subprocess
from pathlib import Path

SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "langfuse_setup.sh"
FUNC_ANCHOR_START = "_fixup_init_user()"
FUNC_ANCHOR_END = "    }"


def _extract_fixup_init_user_body(script_path: Path) -> str:
    """Extract the text of the _fixup_init_user function body from the script.

    Uses awk with symbolic anchors (function name and closing brace) rather than
    line numbers, so the extraction is robust to surrounding edits.
    """
    result = subprocess.run(
        [
            "awk",
            "/^[[:space:]]*_fixup_init_user\\(\\)/{found=1} found{print} found && /^[[:space:]]+\\}$/ && NR>1{exit}",
            str(script_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    body = result.stdout
    assert body, f"Failed to extract _fixup_init_user body from {script_path}"
    return body


class TestFixupInitUserConcatenationRemoved:
    """T1: Verifies the TD-512 bug pattern is absent from _fixup_init_user body."""

    def test_prefix_langfuse_concat_absent_from_function_body(self):
        """_fixup_init_user body must NOT contain the `"$prefix"langfuse` concatenation pattern."""
        body = _extract_fixup_init_user_body(SCRIPT_PATH)
        assert '"$prefix"langfuse' not in body, (
            'TD-512 regression: `"$prefix"langfuse` concat pattern found in '
            "_fixup_init_user body. Expected literal `langfuse` for -U and -d args."
        )


class TestFixupInitUserLiteralPresent:
    """T2: Verifies the Option B fix (literal `langfuse`) is present at both -U and -d positions."""

    def test_dash_u_langfuse_present_exactly_twice(self):
        """-U langfuse must appear exactly twice in _fixup_init_user (one per psql invocation)."""
        body = _extract_fixup_init_user_body(SCRIPT_PATH)
        matches = re.findall(r"-U\s+langfuse\b", body)
        assert len(matches) == 2, (
            f"Expected exactly 2 occurrences of `-U langfuse` in _fixup_init_user body, "
            f"found {len(matches)}. Body excerpt:\n{body[:500]}"
        )

    def test_dash_d_langfuse_present_exactly_twice(self):
        """-d langfuse must appear exactly twice in _fixup_init_user (one per psql invocation)."""
        body = _extract_fixup_init_user_body(SCRIPT_PATH)
        matches = re.findall(r"-d\s+langfuse\b", body)
        assert len(matches) == 2, (
            f"Expected exactly 2 occurrences of `-d langfuse` in _fixup_init_user body, "
            f"found {len(matches)}. Body excerpt:\n{body[:500]}"
        )


class TestFixupInitUserContainerNamePreserved:
    """T3: Verifies the out-of-scope container name construction is unchanged."""

    def test_pg_container_prefix_assignment_preserved(self):
        """pg_container="${prefix}-langfuse-postgres" must remain in the script file (out-of-scope discipline)."""
        script_text = SCRIPT_PATH.read_text()
        assert 'pg_container="${prefix}-langfuse-postgres"' in script_text, (
            'Out-of-scope container name `pg_container="${prefix}-langfuse-postgres"` '
            "is missing from scripts/langfuse_setup.sh. Scope violation — this line "
            "must not be modified by the TD-512 fix."
        )
