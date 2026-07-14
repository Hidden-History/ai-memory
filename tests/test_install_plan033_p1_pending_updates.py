"""PLAN-033 P1 — installer emits a pending-change manifest (BP-188).

When ``_sync_oversight_templates`` (deploy mode) finds an oversight file that is
BOTH user-modified AND changed upstream — the ``n_warn`` "needs-merge" branch —
it additionally emits ``.audit/state/pending-updates.json`` carrying, per entry,
the three-state digest triple ``{old_shipped_hash, deployed_hash,
new_template_hash}`` plus classification / suggested_action / rationale /
severity / order, and manifest-level ``schema_version`` + a content-derived
``manifest_id`` (whole-manifest idempotency) + ``generated_at`` / ``generated_by``
/ ``source_version``.

This is PRODUCER-only and ADDITIVE: the existing loud ``log_warning`` stays, no
user data is mutated, and no other deploy/sync/migrate/new/check behavior
changes. These tests drive the same no-main sourcing harness the sibling
``test_install_oversight_template_sync.py`` uses.
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
    """Copy install.sh minus the final 'main "$@"' line into tmp_path for sourcing."""
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


def _mk_shipped_template(install_dir: Path, rel_path: str, body: str) -> None:
    dest = install_dir / "templates" / "oversight" / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(body, encoding="utf-8")


def _mk_registry(install_dir: Path, rows: list[tuple[str, str]]) -> None:
    reg = install_dir / "templates" / "known-oversight-template-versions.txt"
    reg.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# test registry\n"] + [f"{rel}\t{h}\n" for rel, h in rows]
    reg.write_text("".join(lines), encoding="utf-8")


def _run(
    install_sh_copy, install_dir, project_dir, func
) -> subprocess.CompletedProcess:
    bash_cmd = f"""
set -euo pipefail
export INSTALL_DIR="{install_dir}"
export PROJECT_PATH="{project_dir}"
source "{install_sh_copy}"
INSTALL_DIR="{install_dir}"
PROJECT_PATH="{project_dir}"
{func}
"""
    return subprocess.run(["bash", "-c", bash_cmd], capture_output=True, text=True)


def _deploy(install_sh_copy, install_dir, project_dir):
    return _run(install_sh_copy, install_dir, project_dir, "deploy_oversight_templates")


def _pending_path(project_dir: Path) -> Path:
    return project_dir / ".audit" / "state" / "pending-updates.json"


def _make_both_changed(
    install_sh_no_main, install_dir, project_dir, rel="tracking/task-tracker.md"
):
    """Drive a project into the both-changed (n_warn) state and return the hashes.

    v1 deployed + recorded (base B) -> user edits the copy -> upstream ships v2.
    Returns (rel, base_hash, deployed_hash, new_template_hash).
    """
    _mk_shipped_template(install_dir, rel, "V1\n")
    assert _deploy(install_sh_no_main, install_dir, project_dir).returncode == 0
    base_hash = _sha256("V1\n")  # recorded in the manifest as the last-deployed base

    copy = project_dir / "oversight" / rel
    copy.write_text("MY LOCAL EDITS\n")
    deployed_hash = _sha256("MY LOCAL EDITS\n")

    _mk_shipped_template(install_dir, rel, "V2 STRUCTURAL UPDATE\n")
    new_hash = _sha256("V2 STRUCTURAL UPDATE\n")
    return rel, base_hash, deployed_hash, new_hash


class TestEmitOnBothChanged:
    def test_emit_contains_correct_digest_triple_and_classification(
        self, install_sh_no_main, dirs
    ):
        install_dir, project_dir = dirs
        rel, base, deployed, new = _make_both_changed(
            install_sh_no_main, install_dir, project_dir
        )

        res = _deploy(install_sh_no_main, install_dir, project_dir)
        assert res.returncode == 0, res.stderr

        # Existing behavior preserved: never clobbered + loud warning still fires.
        assert (project_dir / "oversight" / rel).read_text() == "MY LOCAL EDITS\n"
        assert "review + merge" in res.stdout

        manifest = _pending_path(project_dir)
        assert manifest.exists(), "pending-updates.json must be emitted on both-changed"
        doc = json.loads(manifest.read_text())

        assert doc["schema_version"] == "1.0"
        assert doc["generated_by"].startswith("install.sh@")
        assert doc["source_version"]
        assert doc["manifest_id"]
        assert doc["generated_at"].endswith("Z")

        assert len(doc["entries"]) == 1
        e = doc["entries"][0]
        # The three-state digest triple is the load-bearing discriminator.
        assert e["old_shipped_hash"] == base
        assert e["deployed_hash"] == deployed
        assert e["new_template_hash"] == new
        assert e["classification"] == "MANAGED_MERGE_REQUIRED"
        assert e["suggested_action"] == "merge"
        assert e["severity"] == "high"
        assert e["rationale"]
        assert e["id"] == rel
        assert e["path"] == f"oversight/{rel}"
        assert e["order"] == 0

    def test_legacy_pre_manifest_file_yields_empty_old_shipped_hash(
        self, install_sh_no_main, dirs
    ):
        """A file the operator had BEFORE we tracked it (no manifest record, no
        matching registry hash) has no known base B -> old_shipped_hash == ""."""
        install_dir, project_dir = dirs
        rel = "decisions/decision-log.md"
        # Project already carries a user-owned copy; no prior deploy => no manifest,
        # no registry entry for this path.
        copy = project_dir / "oversight" / rel
        copy.parent.mkdir(parents=True)
        copy.write_text("USER DECISIONS\n")
        _mk_shipped_template(install_dir, rel, "SHIPPED STRUCTURE\n")

        res = _deploy(install_sh_no_main, install_dir, project_dir)
        assert res.returncode == 0, res.stderr

        doc = json.loads(_pending_path(project_dir).read_text())
        e = next(x for x in doc["entries"] if x["id"] == rel)
        assert e["old_shipped_hash"] == ""
        assert e["deployed_hash"] == _sha256("USER DECISIONS\n")
        assert e["new_template_hash"] == _sha256("SHIPPED STRUCTURE\n")

    def test_old_shipped_hash_falls_back_to_registry_known_hash(
        self, install_sh_no_main, dirs
    ):
        """No manifest record, but a prior-shipped hash is registered for the path
        -> old_shipped_hash uses that registry base rather than "" (best-effort B)."""
        install_dir, project_dir = dirs
        rel = "plans/PLAN_TEMPLATE.md"
        prior_hash = _sha256("PRIOR SHIPPED\n")
        _mk_registry(install_dir, [(rel, prior_hash)])
        _mk_shipped_template(install_dir, rel, "CURRENT SHIPPED\n")

        # User-modified copy that matches NEITHER shipped nor the known prior hash
        # (so it is a warn, not a migrate) and has no manifest record.
        copy = project_dir / "oversight" / rel
        copy.parent.mkdir(parents=True)
        copy.write_text("LOCALLY EDITED\n")

        res = _deploy(install_sh_no_main, install_dir, project_dir)
        assert res.returncode == 0, res.stderr

        doc = json.loads(_pending_path(project_dir).read_text())
        e = next(x for x in doc["entries"] if x["id"] == rel)
        assert e["old_shipped_hash"] == prior_hash


class TestIdempotency:
    def test_rerun_replaces_never_appends_duplicates(self, install_sh_no_main, dirs):
        install_dir, project_dir = dirs
        _make_both_changed(install_sh_no_main, install_dir, project_dir)

        assert _deploy(install_sh_no_main, install_dir, project_dir).returncode == 0
        first = json.loads(_pending_path(project_dir).read_text())

        # Same drift state on re-run: the whole manifest is REPLACED, not appended.
        assert _deploy(install_sh_no_main, install_dir, project_dir).returncode == 0
        second = json.loads(_pending_path(project_dir).read_text())

        assert len(first["entries"]) == 1
        assert len(second["entries"]) == 1  # no duplicate entry
        assert first["manifest_id"] == second["manifest_id"]  # content-derived, stable
        assert first["entries"] == second["entries"]

    def test_resolved_drift_removes_stale_manifest(self, install_sh_no_main, dirs):
        """Level-triggered: once the drift is gone, a re-run removes the manifest
        so the consumer's presence-of-file discovery reads 'nothing pending'."""
        install_dir, project_dir = dirs
        rel, _, _, _ = _make_both_changed(install_sh_no_main, install_dir, project_dir)

        assert _deploy(install_sh_no_main, install_dir, project_dir).returncode == 0
        assert _pending_path(project_dir).exists()

        # Operator resolves the conflict by taking the shipped version verbatim.
        shipped = install_dir / "templates" / "oversight" / rel
        (project_dir / "oversight" / rel).write_text(shipped.read_text())

        assert _deploy(install_sh_no_main, install_dir, project_dir).returncode == 0
        assert not _pending_path(project_dir).exists()


class TestSchemaVersionGuard:
    def test_reader_accepts_known_major(self, install_sh_no_main, dirs):
        install_dir, project_dir = dirs
        _make_both_changed(install_sh_no_main, install_dir, project_dir)
        assert _deploy(install_sh_no_main, install_dir, project_dir).returncode == 0
        manifest = _pending_path(project_dir)  # freshly emitted at schema 1.0

        res = _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            f'_pending_updates_schema_ok "{manifest}"',
        )
        assert res.returncode == 0, res.stderr

    def test_reader_rejects_unknown_major(self, install_sh_no_main, dirs):
        install_dir, project_dir = dirs
        manifest = _pending_path(project_dir)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        # A manifest written by a hypothetical future MAJOR the installer can't parse.
        manifest.write_text(json.dumps({"schema_version": "99.0", "entries": []}))

        res = _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            f'_pending_updates_schema_ok "{manifest}"',
        )
        assert res.returncode != 0
        assert "unsupported schema_version major 99" in res.stderr

    def test_reader_absent_manifest_is_ok(self, install_sh_no_main, dirs):
        install_dir, project_dir = dirs
        missing = _pending_path(project_dir)
        res = _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            f'_pending_updates_schema_ok "{missing}"',
        )
        assert res.returncode == 0, res.stderr


class TestAdditiveNoRegression:
    def test_no_pending_manifest_when_no_both_changed(self, install_sh_no_main, dirs):
        """A clean deploy (only a new file) emits no pending manifest — absence =
        nothing pending; existing new-file deploy behavior is unchanged."""
        install_dir, project_dir = dirs
        _mk_shipped_template(install_dir, "tracking/task-tracker.md", "V1\n")

        res = _deploy(install_sh_no_main, install_dir, project_dir)
        assert res.returncode == 0, res.stderr
        assert (project_dir / "oversight" / "tracking" / "task-tracker.md").exists()
        assert not _pending_path(project_dir).exists()
