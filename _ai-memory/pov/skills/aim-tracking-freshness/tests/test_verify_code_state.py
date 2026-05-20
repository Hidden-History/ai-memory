"""
Integration tests for --verify-code-state (TD-547, F-1).

Tests use temporary git repos to simulate source code history.
All oversight fixtures are isolated in tmp_path — the live oversight tree is never touched.

Fixtures use realistically-shaped bug file content per
``feedback_realistic_size_production_artifact_tests``.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "tracking_freshness.py"

# Import the module in-process for unit-level tests (token extraction, timeout
# orchestrator) that cannot be exercised efficiently via subprocess.
sys.path.insert(0, str(SCRIPT.parent))
import tracking_freshness as tf  # noqa: E402

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_oversight_with_open_bug(
    tmp_path: Path, bug_id: str, bug_content: str
) -> tuple:
    """Create minimal oversight/ tree with one open bug. Returns (oversight, bugs_dir)."""
    oversight = tmp_path / "oversight"
    bugs_dir = oversight / "bugs"
    td_dir = oversight / "tech-debt"
    bugs_dir.mkdir(parents=True)
    td_dir.mkdir()
    (oversight / "tracking").mkdir()

    (bugs_dir / f"BUG-{bug_id}-test-bug.md").write_text(bug_content, encoding="utf-8")
    (bugs_dir / "INDEX.md").write_text(
        "# Bug Tracker Index\n\n"
        "## Open\n\n"
        f"| BUG-{bug_id} | Test bug | OPEN |"
        f" [file](./BUG-{bug_id}-test-bug.md) |\n\n"
        "## Closed Bugs\n\n",
        encoding="utf-8",
    )
    (td_dir / "INDEX.md").write_text(
        "# Technical Debt Index\n\n"
        "## Open Technical Debt\n\n"
        "## Closed Technical Debt\n\n",
        encoding="utf-8",
    )
    # Minimal decision-log so F-2 check is silent
    (oversight / "tracking" / "decision-log.md").write_text(
        "# Decision Log\n\n**Last Updated**: 2099-01-01 (no decisions.)\n\n---\n\n",
        encoding="utf-8",
    )
    return oversight, bugs_dir


def _git_init_main(repo: Path) -> None:
    """Initialise a git repo with main as the default branch."""
    result = subprocess.run(
        ["git", "init", "-b", "main", str(repo)], capture_output=True
    )
    if result.returncode != 0:
        subprocess.run(["git", "init", str(repo)], capture_output=True, check=True)
        subprocess.run(
            ["git", "symbolic-ref", "HEAD", "refs/heads/main"],
            cwd=str(repo),
            capture_output=True,
        )


def _make_fake_repo(
    tmp_path: Path, commit_msg: str, touched_file: str = "scripts/install.sh"
) -> Path:
    """Create a minimal git repo on main with an initial commit and a fix commit.

    The initial commit is required so the fix commit has a parent — git diff-tree
    returns no files for root commits (no parent), which breaks path-overlap scoring.
    """
    repo = tmp_path / "fake-repo"
    repo.mkdir()
    _git_init_main(repo)
    for cmd in [
        ["git", "config", "user.email", "test@example.com"],
        ["git", "config", "user.name", "Test"],
    ]:
        subprocess.run(cmd, cwd=str(repo), capture_output=True, check=True)

    # Initial commit gives the fix commit a parent so diff-tree works.
    (repo / "README.md").write_text("initial", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "chore: initial commit"],
        cwd=str(repo),
        capture_output=True,
        check=True,
    )

    file_path = repo / touched_file
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("content", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", commit_msg],
        cwd=str(repo),
        capture_output=True,
        check=True,
    )
    return repo


def _run_verify(oversight: Path, source_repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--check",
            "--oversight-root",
            str(oversight),
            "--verify-code-state",
            "--source-repo",
            str(source_repo),
        ],
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# F1-1: HIGH confidence
# ---------------------------------------------------------------------------


class TestVerifyCodeStateHighConfidence:
    def test_high_confidence_phantom_open(self, tmp_path: Path) -> None:
        """Bug Status OPEN + fix commit on main + file-path overlap + mtime predates → HIGH."""
        bug_content = (
            "# BUG-273: Install fails — readonly UID/GID sourced into env\n\n"
            "**Status**: OPEN\n"
            "**Severity**: HIGH\n\n"
            "## Summary\n\n"
            "The install script sources .env which includes readonly UID/GID pairs "
            "from the host system, causing install to fail on certain Linux configurations.\n\n"
            "## Affected files\n\n"
            "- scripts/install.sh (main installer — filters env before export)\n\n"
            "## Reproduction\n\n"
            "Run `./scripts/install.sh /path/to/project` on a system where UID/GID\n"
            "are set to readonly. The installer crashes at the env-source step.\n\n"
            "## Expected fix target\n\n"
            "Filter UID and GID keys before sourcing .env in scripts/install.sh.\n"
        )
        oversight, bugs_dir = _make_oversight_with_open_bug(
            tmp_path, "273", bug_content
        )
        source_repo = _make_fake_repo(
            tmp_path,
            "fix(install): filter readonly UID/GID from .env source (BUG-273)",
            "scripts/install.sh",
        )

        # Set bug file mtime to 1 day ago so it predates the commit
        bug_path = bugs_dir / "BUG-273-test-bug.md"
        past = time.time() - 86400
        os.utime(bug_path, (past, past))

        result = _run_verify(oversight, source_repo)
        assert "HIGH confidence" in result.stdout, (
            f"Expected HIGH confidence section.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "BUG-273" in result.stdout
        assert "PHANTOM-OPEN CANDIDATES" in result.stdout


# ---------------------------------------------------------------------------
# F1-2: MEDIUM confidence — commit exists, no file-path overlap
# ---------------------------------------------------------------------------


class TestVerifyCodeStateMediumConfidence:
    def test_medium_confidence_no_file_path_overlap(self, tmp_path: Path) -> None:
        """Bug Status OPEN + fix commit on main + no file-path in bug body → MEDIUM."""
        bug_content = (
            "# BUG-274: User-input env vars not persisted across reinstall\n\n"
            "**Status**: OPEN\n"
            "**Severity**: HIGH\n\n"
            "## Summary\n\n"
            "When a user provides custom env vars during install, they are applied\n"
            "for the current session but not written to the persistent .env file.\n"
            "A subsequent reinstall loses all user configuration.\n\n"
            "## Steps to reproduce\n\n"
            "1. Run install with CUSTOM_VAR=foo\n"
            "2. Reinstall from scratch\n"
            "3. CUSTOM_VAR is no longer set\n\n"
            "## Fix approach\n\n"
            "Persist any user-provided vars to the .env file at install time.\n"
        )
        # Bug body has no lines starting with - or * that contain file paths
        oversight, bugs_dir = _make_oversight_with_open_bug(
            tmp_path, "274", bug_content
        )
        source_repo = _make_fake_repo(
            tmp_path,
            "fix(install): persist user-input env vars to .env files (BUG-274)",
            "scripts/env_writer.py",
        )

        # Mtime predates commit
        bug_path = bugs_dir / "BUG-274-test-bug.md"
        past = time.time() - 86400
        os.utime(bug_path, (past, past))

        result = _run_verify(oversight, source_repo)
        assert "MEDIUM confidence" in result.stdout, (
            f"Expected MEDIUM confidence section.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "BUG-274" in result.stdout
        assert "HIGH confidence" not in result.stdout


# ---------------------------------------------------------------------------
# F1-3: LOW confidence — inline evidence but no commit on main
# ---------------------------------------------------------------------------


class TestVerifyCodeStateLowConfidence:
    def test_low_confidence_pr_cited_not_in_git_log(self, tmp_path: Path) -> None:
        """Bug cites PR #131 but no BUG-275 commits exist in git → LOW bucket."""
        bug_content = (
            "# BUG-275: Config not read from split env files\n\n"
            "**Status**: OPEN — fix research-validated PM #267, dispatch Wave 5 PM #268\n"
            "**Severity**: HIGH\n\n"
            "## Summary\n\n"
            "MemoryConfig does not read from the split docker/.env + .env.secrets pattern\n"
            "introduced in v2.0.7. Only the monolithic .env is read, leaving all\n"
            "secrets-class keys undefined at runtime.\n\n"
            "## Fix dispatched\n\n"
            "Fix dispatched via PR #131 in Wave 5 as part of PM #268 sprint.\n"
            "SHA d04d998 references this issue in the commit log.\n\n"
            "## Affected files\n\n"
            "- memory/config.py (MemoryConfig loader)\n"
        )
        oversight, _ = _make_oversight_with_open_bug(tmp_path, "275", bug_content)

        # Repo exists but has NO commits mentioning BUG-275
        # (do not include the literal record-id anywhere in the commit message —
        # `git log --grep=BUG-275` would otherwise match and lift confidence)
        source_repo = _make_fake_repo(
            tmp_path,
            "chore: initial repository setup",
            "README.md",
        )

        result = _run_verify(oversight, source_repo)
        assert "LOW confidence" in result.stdout, (
            f"Expected LOW confidence section (PR cited, no commit on main).\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "BUG-275" in result.stdout


# ---------------------------------------------------------------------------
# F1-4: Revert on main downgrades to LOW
# ---------------------------------------------------------------------------


class TestVerifyCodeStateRevertDowngrades:
    def test_revert_on_main_downgrades_to_low(self, tmp_path: Path) -> None:
        """Fix commit + revert commit both on main → LOW (not HIGH or MEDIUM)."""
        bug_content = (
            "# BUG-277: Secrets not moved to .env.secrets (chmod 600)\n\n"
            "**Status**: OPEN — fix path Path B … Wave 6 implementation PM #271\n"
            "**Severity**: HIGH\n\n"
            "## Summary\n\n"
            "25 secret-class keys remain in the world-readable .env file.\n"
            "They must be moved to .env.secrets with chmod 600 at install time.\n\n"
            "## Affected files\n\n"
            "- scripts/install.sh (secrets split logic)\n"
        )
        oversight, bugs_dir = _make_oversight_with_open_bug(
            tmp_path, "277", bug_content
        )

        repo = tmp_path / "fake-repo-revert"
        repo.mkdir()
        _git_init_main(repo)
        for cmd in [
            ["git", "config", "user.email", "t@t.com"],
            ["git", "config", "user.name", "T"],
        ]:
            subprocess.run(cmd, cwd=str(repo), capture_output=True, check=True)

        # Initial commit
        (repo / "README.md").write_text("init", encoding="utf-8")
        subprocess.run(
            ["git", "add", "."], cwd=str(repo), capture_output=True, check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(repo),
            capture_output=True,
            check=True,
        )

        # Fix commit
        (repo / "scripts").mkdir()
        (repo / "scripts" / "install.sh").write_text("fixed", encoding="utf-8")
        subprocess.run(
            ["git", "add", "."], cwd=str(repo), capture_output=True, check=True
        )
        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                "fix(install): move 25 secret-class keys to .env.secrets chmod 600 (BUG-277)",
            ],
            cwd=str(repo),
            capture_output=True,
            check=True,
        )

        # Revert commit — covers the fix
        (repo / "scripts" / "install.sh").write_text("reverted", encoding="utf-8")
        subprocess.run(
            ["git", "add", "."], cwd=str(repo), capture_output=True, check=True
        )
        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                'Revert "fix(install): move 25 secret-class keys to .env.secrets chmod 600 (BUG-277)"',
            ],
            cwd=str(repo),
            capture_output=True,
            check=True,
        )

        # Mtime set to past so it predates any commit
        bug_path = bugs_dir / "BUG-277-test-bug.md"
        past = time.time() - 86400
        os.utime(bug_path, (past, past))

        result = _run_verify(oversight, repo)
        assert "LOW confidence" in result.stdout, (
            f"Expected LOW (revert on main downgrades confidence).\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "HIGH confidence" not in result.stdout
        assert "MEDIUM confidence" not in result.stdout


# ---------------------------------------------------------------------------
# F1-5: Missing source repo — graceful skip, section absent
# ---------------------------------------------------------------------------


class TestVerifyCodeStateNoRepoGraceful:
    def test_missing_source_repo_skips_section(self, tmp_path: Path) -> None:
        """--source-repo pointing to nonexistent path → section absent, exit unaffected."""
        bug_content = (
            "# BUG-280: Some Open Bug\n\n"
            "**Status**: OPEN\n"
            "**Severity**: MEDIUM\n\n"
            "## Summary\n\nTest fixture for graceful-skip verification.\n"
        )
        oversight, _ = _make_oversight_with_open_bug(tmp_path, "280", bug_content)
        nonexistent = tmp_path / "does-not-exist"

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--check",
                "--oversight-root",
                str(oversight),
                "--verify-code-state",
                "--source-repo",
                str(nonexistent),
            ],
            capture_output=True,
            text=True,
        )
        assert (
            "PHANTOM-OPEN CANDIDATES" not in result.stdout
        ), "Section must be absent when source repo is missing."
        assert "NOTE" in result.stderr
        assert "source repo not resolved" in result.stderr


# ---------------------------------------------------------------------------
# F1-6: --verify-code-state does not modify existing oversight files
# ---------------------------------------------------------------------------


class TestVerifyCodeStateDoesNotModifyFiles:
    def test_existing_oversight_files_not_modified(self, tmp_path: Path) -> None:
        """Running --verify-code-state --check must not modify any pre-existing oversight files."""
        bug_content = (
            "# BUG-281: Config loader ignores .env.secrets\n\n"
            "**Status**: OPEN\n"
            "**Severity**: MEDIUM\n\n"
            "## Summary\n\n"
            "The MemoryConfig loader only reads .env, ignoring the secrets file.\n\n"
            "## Affected files\n\n"
            "- memory/config.py (MemoryConfig.load)\n"
        )
        oversight, _bugs_dir = _make_oversight_with_open_bug(
            tmp_path, "281", bug_content
        )
        source_repo = _make_fake_repo(
            tmp_path,
            "fix(config): read split docker/.env + .env.secrets in MemoryConfig (BUG-281)",
            "memory/config.py",
        )

        # Snapshot mtimes of existing files before run
        existing_files = {
            p: p.stat().st_mtime for p in oversight.rglob("*") if p.is_file()
        }

        _run_verify(oversight, source_repo)

        for path, mtime_before in existing_files.items():
            assert (
                path.stat().st_mtime == mtime_before
            ), f"Existing file was unexpectedly modified: {path}"


# ---------------------------------------------------------------------------
# F-2: EVIDENCE-TIMEOUT bucket (spec §4.7 row 4)
# ---------------------------------------------------------------------------


class TestEvidenceTimeoutBucket:
    def test_git_timeout_produces_evidence_timeout_bucket(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """Per-record git timeout → EVIDENCE-TIMEOUT bucket, NOT silent LOW/no-result.

        Monkeypatches ``tracking_freshness._run_git`` to simulate every git
        invocation hitting ``subprocess.TimeoutExpired``.  Verifies that the
        record is routed to the EVIDENCE-TIMEOUT bucket and that no confidence
        classification (HIGH/MEDIUM/LOW) is emitted for it.
        """
        bug_content = (
            "# BUG-298: Some open bug for timeout-bucket coverage\n\n"
            "**Status**: OPEN\n"
            "**Severity**: MEDIUM\n\n"
            "## Summary\n\nFixture verifies EVIDENCE-TIMEOUT bucket routing.\n\n"
            "## Affected files\n\n"
            "- scripts/install.sh (handler)\n"
        )
        oversight, bugs_dir = _make_oversight_with_open_bug(
            tmp_path, "298", bug_content
        )
        # Real repo so resolve_source_repo() succeeds; queries inside it will be
        # short-circuited by the monkeypatched _run_git.
        source_repo = _make_fake_repo(
            tmp_path,
            "chore: unrelated initial setup",
            "README.md",
        )

        # Simulate timeout on every git invocation (success=False, stdout="",
        # did_timeout=True).
        monkeypatch.setattr(tf, "_run_git", lambda *a, **kw: (False, "", True))

        record = tf.parse_record_file(bugs_dir / "BUG-298-test-bug.md", "bug")
        open_records_with_dirs = [(record, bugs_dir)]

        args = argparse.Namespace(
            check=True,
            write=False,
            oversight_root=str(oversight),
            verify_code_state=True,
            source_repo=str(source_repo),
            last_n_sessions=None,
            bug_id=None,
        )

        tf.run_verify_code_state(open_records_with_dirs, source_repo, oversight, args)

        captured = capsys.readouterr()
        assert "EVIDENCE-TIMEOUT" in captured.out, (
            f"Expected EVIDENCE-TIMEOUT section.\n"
            f"stdout: {captured.out}\nstderr: {captured.err}"
        )
        assert "BUG-298" in captured.out
        # Classification must be skipped, not silently fall through to LOW.
        assert "HIGH confidence" not in captured.out
        assert "MEDIUM confidence" not in captured.out
        assert "LOW confidence" not in captured.out

        # Sidecar must surface the bucket too.
        sidecar = oversight / "reports" / "PHANTOM-OPEN-CANDIDATES.md"
        assert sidecar.exists()
        sidecar_text = sidecar.read_text(encoding="utf-8")
        assert "EVIDENCE-TIMEOUT" in sidecar_text
        assert "BUG-298" in sidecar_text


# ---------------------------------------------------------------------------
# F-5: Version-string token class (spec §4.1 Step A row 3)
# ---------------------------------------------------------------------------


class TestExtractEvidenceTokensVersions:
    def test_version_strings_extracted_per_spec(self) -> None:
        """``v\\d+\\.\\d+\\.\\d+`` tokens captured alongside SHAs/PRs/file-paths."""
        text = (
            "# BUG-999: Some bug\n\n"
            "**Status**: OPEN\n\n"
            "Affected versions: v2.4.0, v2.4.1\n"
            "Fix target: v3.0.0\n"
            "Note: V2 should NOT match (uppercase, not lowercase v).\n"
            "Note: v2.4 should NOT match (only two components).\n"
        )
        tokens = tf.extract_evidence_tokens(text, "999", "bug")
        assert tokens["versions"] == {
            "v2.4.0",
            "v2.4.1",
            "v3.0.0",
        }, f"Unexpected versions set: {tokens['versions']}"

    def test_version_tokens_dict_key_present_when_none_match(self) -> None:
        """``versions`` key is always present in the result dict (empty set when none)."""
        text = (
            "# BUG-001: No versions cited here\n\n"
            "**Status**: OPEN\n\n"
            "## Summary\n\nNothing to see.\n"
        )
        tokens = tf.extract_evidence_tokens(text, "001", "bug")
        assert "versions" in tokens
        assert tokens["versions"] == set()
