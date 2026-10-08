"""Oversight-template writes: crash atomicity (TD-825) and an honest pending manifest (TD-850).

Both records are absorbed by Story 1.2 because forcing conversion on every
install is what makes them reachable at scale: every never-converted install
becomes a legacy case that deploys oversight templates for the first time.

TD-825 -- the three deploy paths (new file, stale-unmodified sync,
stale-migrate) wrote with a bare ``cp``, which truncates the destination and
then fills it. A crash mid-write leaves a hybrid file, half old oversight
record and half new template, with nothing to say so.

TD-850 -- every manifest entry was stamped ``MANAGED_MERGE_REQUIRED`` / ``high``
/ ``merge`` from a hardcoded literal, and the row was appended even for drift
the operator had already disposed of in the ledger. A report that asks for a
three-way merge on nearly every entry is not a report.
"""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
_INSTALL_SH = _SCRIPTS_DIR / "install.sh"
_HELPERS = _SCRIPTS_DIR / "_env_split_helpers.sh"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture
def install_sh_no_main(tmp_path) -> Path:
    content = _INSTALL_SH.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    assert lines[-1].strip() == 'main "$@"', (
        f"Expected last line 'main \"$@\"', got: {lines[-1]!r}. "
        "If install.sh structure changed, update this fixture."
    )
    copy = tmp_path / "install.sh"
    copy.write_text("".join(lines[:-1]), encoding="utf-8")
    copy.chmod(0o755)
    shutil.copy(_HELPERS, tmp_path / "_env_split_helpers.sh")
    return copy


@pytest.fixture
def dirs(tmp_path):
    install_dir = tmp_path / "install_dir"
    project_dir = tmp_path / "project_dir"
    install_dir.mkdir()
    project_dir.mkdir()
    return install_dir, project_dir


def _bash_env(tmp_path: Path) -> dict[str, str]:
    """Allowlisted environment, built from scratch -- see the sibling install module."""
    import os

    home = tmp_path / "fake_home"
    home.mkdir(exist_ok=True)
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }


def _mk_shipped_template(install_dir: Path, rel_path: str, body: str) -> None:
    dest = install_dir / "templates" / "oversight" / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(body, encoding="utf-8")


def _run(install_sh_copy, install_dir, project_dir, tmp_path, func):
    bash_cmd = f"""
set -euo pipefail
export INSTALL_DIR="{install_dir}"
export PROJECT_PATH="{project_dir}"
source "{install_sh_copy}"
INSTALL_DIR="{install_dir}"
PROJECT_PATH="{project_dir}"
{func}
"""
    return subprocess.run(
        ["bash", "-c", bash_cmd],
        capture_output=True,
        text=True,
        env=_bash_env(tmp_path),
    )


def _deploy(install_sh_copy, install_dir, project_dir, tmp_path):
    return _run(
        install_sh_copy,
        install_dir,
        project_dir,
        tmp_path,
        "deploy_oversight_templates",
    )


# ---------------------------------------------------------------------------
# TD-825 -- crash-atomic template writes.
# ---------------------------------------------------------------------------


class TestTemplateWritesArePublishedByRename:
    """The invariant is adopted from reconcile_engine.py::atomic_write (BP-187 §4),
    not designed here: temp file in the SAME directory -> fsync -> os.replace ->
    directory fsync.

    THE INODE IS THE OBSERVABLE, and it is why this test is deterministic rather
    than a race. A bare ``cp`` opens the destination with O_TRUNC and writes in
    place, so the destination keeps its inode and is observably truncated for the
    duration. A rename publishes a DIFFERENT inode that was already complete
    before it became visible under the destination's name. Asserting the inode
    changed is therefore asserting that no in-place truncation window existed,
    without having to win a race against one.
    """

    _REL = "tracking/task-tracker.md"

    def test_a_sync_deploy_replaces_the_inode_rather_than_truncating_in_place(
        self, install_sh_no_main, dirs, tmp_path
    ):
        install_dir, project_dir = dirs
        _mk_shipped_template(install_dir, self._REL, "V1\n")
        assert (
            _deploy(install_sh_no_main, install_dir, project_dir, tmp_path).returncode
            == 0
        )

        dest = project_dir / "oversight" / self._REL
        before_inode = dest.stat().st_ino

        # Unmodified since the recorded deploy -> the auto-sync path.
        _mk_shipped_template(install_dir, self._REL, "V2 STRUCTURAL UPDATE\n")
        res = _deploy(install_sh_no_main, install_dir, project_dir, tmp_path)
        assert res.returncode == 0, res.stderr

        assert dest.read_text(encoding="utf-8") == "V2 STRUCTURAL UPDATE\n"
        assert dest.stat().st_ino != before_inode, (
            "the destination kept its inode, so it was written in place -- there "
            "was a window in which it held a truncated hybrid"
        )

    def test_a_failed_write_leaves_the_original_intact_and_no_temp_behind(
        self, install_sh_no_main, dirs, tmp_path
    ):
        """The other half of the invariant: never publish a partial destination.

        The write is failed by pointing it at a source that cannot be read as a
        file. What matters is not the specific failure but that the destination
        is not touched by one, and that the temp file does not survive it.
        """
        install_dir, project_dir = dirs
        dest = project_dir / "oversight" / self._REL
        dest.parent.mkdir(parents=True)
        dest.write_text("ORIGINAL CONTENT\n", encoding="utf-8")

        bad_src = install_dir / "not-a-file"
        bad_src.mkdir()

        res = _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            # The existence check is not ceremony. Without it a missing helper is
            # "command not found", which is also non-zero and also leaves the
            # destination alone -- so the test passed at baseline, where the
            # helper did not exist at all, for entirely the wrong reason.
            'declare -F _atomic_install_file > /dev/null || { echo "helper_missing=1"; exit 9; }\n'
            f'_atomic_install_file "{bad_src}" "{dest}" || echo "helper_failed=1"',
        )
        combined = res.stdout + res.stderr
        assert "helper_missing=1" not in combined, combined
        assert "helper_failed=1" in combined, combined
        assert dest.read_text(encoding="utf-8") == "ORIGINAL CONTENT\n"
        leftovers = [p.name for p in dest.parent.glob("*.tmp")]
        assert not leftovers, f"temp files survived a failed write: {leftovers}"

    def test_no_deploy_path_still_writes_with_a_bare_cp(self, install_sh_no_main):
        """The mechanism assertion, kept alongside the behavioural ones because it
        names the defect directly: three bare ``cp`` calls on the three deploy
        paths. The fourth branch -- both-changed / needs-merge -- must still not
        copy at all; it is the genuinely no-clobber path and re-introducing a copy
        there would silently clobber user data.
        """
        body = subprocess.run(
            [
                "bash",
                "-c",
                f'source "{install_sh_no_main}"; declare -f _sync_oversight_templates',
            ],
            capture_output=True,
            text=True,
        )
        assert body.returncode == 0, body.stdout + body.stderr
        copies = [
            line.strip()
            for line in body.stdout.splitlines()
            if line.strip().startswith("cp ")
        ]
        assert not copies, f"a bare cp survives on a deploy path: {copies}"
        assert "_atomic_install_file" in body.stdout


# ---------------------------------------------------------------------------
# TD-850 -- the pending manifest stops over-firing.
# ---------------------------------------------------------------------------


def _emit_manifest(install_sh_copy, install_dir, project_dir, tmp_path, rows):
    """Drive the manifest emitter directly over a chosen set of digest triples.

    Driving the emitter rather than the whole sync is deliberate: the
    classification is a pure function of the triple, and reaching each triple
    through a real deploy would take three separate multi-run fixtures to prove
    one thing about each.
    """
    tsv = tmp_path / "entries.tsv"
    tsv.write_text(
        "".join(f"{rel}\t{old}\t{dep}\t{new}\n" for rel, old, dep, new in rows),
        encoding="utf-8",
    )
    out = project_dir / ".audit" / "state" / "pending-updates.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    res = _run(
        install_sh_copy,
        install_dir,
        project_dir,
        tmp_path,
        f'_write_pending_updates "{out}" "{tsv}" "install.sh@test" "test"',
    )
    assert res.returncode == 0, res.stdout + res.stderr
    return {e["id"]: e for e in json.loads(out.read_text())["entries"]}


class TestTheManifestClassifiesFromTheDigestTriple:
    """The first over-fire. ``classification`` was a hardcoded literal on the line
    beside ``old_shipped_hash``, applied to every entry regardless of any hash --
    so populating the hash alone would have changed nothing, and the intake's
    stated cause was incomplete.
    """

    def test_an_entry_with_no_identifiable_base_is_not_asked_to_merge(
        self, install_sh_no_main, dirs, tmp_path
    ):
        """A three-way merge needs a base. With none, asking for one asks the
        operator for something nobody can perform. This is the largest bucket:
        every legacy pre-manifest file is in it.
        """
        install_dir, project_dir = dirs
        entries = _emit_manifest(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            [("legacy.md", "", _sha256("local"), _sha256("new"))],
        )
        assert entries["legacy.md"]["classification"] == "BASE_UNKNOWN"
        assert entries["legacy.md"]["suggested_action"] == "review"
        assert entries["legacy.md"]["severity"] == "low"

    def test_an_entry_whose_template_did_not_move_is_not_asked_to_merge(
        self, install_sh_no_main, dirs, tmp_path
    ):
        """Base known and equal to the new template: only the project copy moved.
        That is local drift, and there is nothing upstream to adopt.
        """
        install_dir, project_dir = dirs
        same = _sha256("template")
        entries = _emit_manifest(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            [("unchanged-upstream.md", same, _sha256("local"), same)],
        )
        assert entries["unchanged-upstream.md"]["classification"] == "LOCAL_DRIFT_ONLY"
        assert entries["unchanged-upstream.md"]["suggested_action"] == "review"

    def test_a_genuinely_both_changed_entry_is_still_a_merge(
        self, install_sh_no_main, dirs, tmp_path
    ):
        """The negative control. Narrowing the classification is only correct if
        the real conflicts survive it -- otherwise the fix is just silence.
        """
        install_dir, project_dir = dirs
        entries = _emit_manifest(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            [("real-conflict.md", _sha256("v1"), _sha256("local"), _sha256("v2"))],
        )
        assert entries["real-conflict.md"]["classification"] == "MANAGED_MERGE_REQUIRED"
        assert entries["real-conflict.md"]["suggested_action"] == "merge"
        assert entries["real-conflict.md"]["severity"] == "high"

    def test_a_mixed_corpus_yields_only_the_real_merges_and_still_surfaces_everything(
        self, install_sh_no_main, dirs, tmp_path
    ):
        """The record's own target, in miniature: the merges must fall to the
        genuinely-conflicted entries, and every other file must still be
        SURFACED. The over-fire was in what the entries claimed, never in which
        files appeared -- a fix that dropped the quiet ones would trade a
        useless report for a lying one.
        """
        install_dir, project_dir = dirs
        rows = [(f"legacy-{i}.md", "", _sha256("l"), _sha256("n")) for i in range(29)]
        same = _sha256("t")
        rows += [(f"static-{i}.md", same, _sha256("l"), same) for i in range(11)]
        rows += [
            (
                f"conflict-{i}.md",
                _sha256("v1"),
                _sha256("local"),
                _sha256("v2"),
            )
            for i in range(3)
        ]
        rows += [
            (
                "knowledge/best-practices/index.md",
                _sha256("v1"),
                _sha256("local"),
                _sha256("v2"),
            )
        ]

        entries = _emit_manifest(
            install_sh_no_main, install_dir, project_dir, tmp_path, rows
        )

        merges = [
            e
            for e in entries.values()
            if e["classification"] == "MANAGED_MERGE_REQUIRED"
        ]
        assert len(merges) == 4, sorted(e["id"] for e in merges)
        assert len(entries) == len(rows), "every entry must still be surfaced"
        assert (
            entries["knowledge/best-practices/index.md"]["classification"]
            == "MANAGED_MERGE_REQUIRED"
        )


class TestAnAlreadyReconciledEntryIsNotReAppended:
    """The second over-fire, and it is independent of the first: the manifest row
    was appended without consulting ``reconciled``, so drift the operator had
    already disposed of in the ledger came back on every deploy. The warn path
    already treated it as "no action"; the manifest is the surface that ASKS for
    the action, so it has to agree.
    """

    _REL = "tracking/task-tracker.md"

    def _plant_helper(self, install_dir: Path, disposed: bool) -> None:
        """Stand in for the shipped reconcile_helper at the path install.sh reads.

        Planting a file at the real path is used rather than shadowing ``python3``
        so the call itself -- argv, exit status, stdout -- is exercised as shipped.
        """
        helper = (
            install_dir
            / "_ai-memory/pov/skills/aim-content-drift/scripts/reconcile_helper.py"
        )
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text(
            "import sys\n"
            + ("print('applied')\nsys.exit(0)\n" if disposed else "sys.exit(1)\n"),
            encoding="utf-8",
        )

    def _drive_to_both_changed(
        self, install_sh_no_main, install_dir, project_dir, tmp_path
    ):
        _mk_shipped_template(install_dir, self._REL, "V1\n")
        assert (
            _deploy(install_sh_no_main, install_dir, project_dir, tmp_path).returncode
            == 0
        )
        (project_dir / "oversight" / self._REL).write_text(
            "MY LOCAL EDITS\n", encoding="utf-8"
        )
        _mk_shipped_template(install_dir, self._REL, "V2 STRUCTURAL UPDATE\n")

    def test_a_disposed_entry_is_absent_from_the_manifest(
        self, install_sh_no_main, dirs, tmp_path
    ):
        install_dir, project_dir = dirs
        self._drive_to_both_changed(
            install_sh_no_main, install_dir, project_dir, tmp_path
        )
        self._plant_helper(install_dir, disposed=True)

        res = _deploy(install_sh_no_main, install_dir, project_dir, tmp_path)
        assert res.returncode == 0, res.stderr
        assert "already reconciled" in res.stdout + res.stderr

        manifest = project_dir / ".audit" / "state" / "pending-updates.json"
        ids = (
            [e["id"] for e in json.loads(manifest.read_text())["entries"]]
            if manifest.exists()
            else []
        )
        assert self._REL not in ids, (
            "a drift the operator already disposed of was re-appended to the "
            f"manifest: {ids}"
        )

    def test_an_undisposed_entry_is_still_appended(
        self, install_sh_no_main, dirs, tmp_path
    ):
        """The negative control: gating on ``reconciled`` must not silence real
        pending drift.
        """
        install_dir, project_dir = dirs
        self._drive_to_both_changed(
            install_sh_no_main, install_dir, project_dir, tmp_path
        )
        self._plant_helper(install_dir, disposed=False)

        res = _deploy(install_sh_no_main, install_dir, project_dir, tmp_path)
        assert res.returncode == 0, res.stderr

        manifest = project_dir / ".audit" / "state" / "pending-updates.json"
        assert manifest.exists(), "undisposed both-changed drift must still be emitted"
        ids = [e["id"] for e in json.loads(manifest.read_text())["entries"]]
        assert self._REL in ids, ids
