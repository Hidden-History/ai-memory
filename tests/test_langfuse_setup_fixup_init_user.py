"""
Regression tests for TD-512: langfuse_setup.sh _fixup_init_user postgres role/db concatenation fix.

Verifies that the `_fixup_init_user` function body uses literal `langfuse` (not
any `$prefix`-adjacent variant) for psql -U and -d arguments, and that all
out-of-scope `$prefix` uses (container name, worker filters, volume names) are
preserved unchanged.

Tests operate on the script source text — no bash execution required.
"""

import re
import subprocess
from pathlib import Path

SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "langfuse_setup.sh"
FUNC_ANCHOR_START = "_fixup_init_user\\(\\)"  # awk regex — parens escaped
FUNC_ANCHOR_END = "\\}"  # awk regex — brace escaped


def _extract_fixup_init_user_body(script_path: Path) -> str:
    """Extract the text of the _fixup_init_user function body from the script.

    Uses awk with symbolic anchors (function name and closing brace) rather than
    line numbers, so the extraction is robust to surrounding edits.
    """
    result = subprocess.run(
        [
            "awk",
            f"/^[[:space:]]*{FUNC_ANCHOR_START}/{{found=1}} found{{print}} found && /^[[:space:]]+{FUNC_ANCHOR_END}$/{{exit}}",
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
        assert not re.search(r'\$\{?prefix\}?[_-]?"?langfuse(?![-_a-z])', body), (
            "TD-512 regression: $prefix-adjacent-to-langfuse pattern found in "
            "_fixup_init_user body. Expected literal `langfuse` for -U and -d args."
        )


class TestFixupInitUserLiteralPresent:
    """T2: Verifies the Option B fix (literal `langfuse`) is present at both -U and -d positions."""

    def test_dash_u_langfuse_present_exactly_twice(self):
        """-U langfuse must appear exactly twice in _fixup_init_user (one per psql invocation)."""
        body = _extract_fixup_init_user_body(SCRIPT_PATH)
        matches = re.findall(r'-U\s+"?langfuse"?(\s|$)', body)
        assert len(matches) == 2, (
            f'Expected exactly 2 occurrences of `-U ["?]langfuse["?]` in _fixup_init_user body, '
            f"found {len(matches)}. Body excerpt:\n{body[:500]}"
        )

    def test_dash_d_langfuse_present_exactly_twice(self):
        """-d langfuse must appear exactly twice in _fixup_init_user (one per psql invocation)."""
        body = _extract_fixup_init_user_body(SCRIPT_PATH)
        matches = re.findall(r'-d\s+"?langfuse"?(\s|$)', body)
        assert len(matches) == 2, (
            f'Expected exactly 2 occurrences of `-d ["?]langfuse["?]` in _fixup_init_user body, '
            f"found {len(matches)}. Body excerpt:\n{body[:500]}"
        )


_OUT_OF_SCOPE_PREFIX_USES = [
    'pg_container="${prefix}-langfuse-postgres"',
    "name=${prefix}-langfuse-worker",
    "name=${prefix}-trace-flush-worker",
    '"${prefix}_langfuse-postgres-data"',
    '"${prefix}_langfuse-clickhouse-data"',
    '"${prefix}_langfuse-redis-data"',
    '"${prefix}_langfuse-minio-data"',
]


class TestOutOfScopePrefixUsesPreserved:
    """T3: Verifies all out-of-scope $prefix uses are unchanged (scope discipline)."""

    def test_out_of_scope_prefix_uses_preserved(self):
        """All 7 out-of-scope $prefix sites from recommendation-first.md §B must remain in the script."""
        script_text = SCRIPT_PATH.read_text()
        for expected in _OUT_OF_SCOPE_PREFIX_USES:
            assert expected in script_text, (
                f"Out-of-scope `$prefix` use `{expected}` is missing from "
                f"scripts/langfuse_setup.sh. Scope violation — TD-512 fix "
                f"must not touch this site."
            )
