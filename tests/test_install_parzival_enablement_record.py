"""Install tests for the Parzival enablement record: value + cause + condition.

Story 1.1 / AD-32: a persisted state records its *cause*, and a flag written from
two causes is never read as a boolean. The installer writes three flat keys into
$INSTALL_DIR/docker/.env at every site that touches enablement:

    PARZIVAL_ENABLED            true | false
    PARZIVAL_ENABLED_CAUSE      opt-out | failed | "" (empty when enabled)
    PARZIVAL_ENABLED_CONDITION  complete | partial

Five write-sites are covered here: four ``false``-writes (package absent,
non-interactive skip, deploy failure, interactive decline) plus the single
``true``-write inside ``configure_parzival_env``.

The v2.0.5->v2.0.6 migration is deliberately NOT a sixth record write-site and has
no test here, because it no longer writes the record at all. An earlier revision of
this docstring claimed it "is exercised in its own test module"; no such module
existed, so a false statement stood guard over an untested site. The migration now
seeds only ``PARZIVAL_ENABLED`` -- it cannot know a cause, and seeding one would
either manufacture ``opt-out`` for a failed install or write the forbidden
(enabled x non-empty cause) cell directly, since ``update_env_file`` appends per
key. See ``scripts/migrate_v205_to_v206.py::PARZIVAL_VARS`` for the full reasoning
and ``tests/test_parzival_migration_seeds_no_cause.py`` for the assertion.

Harness note (TR section *Harness*): the story names two mechanisms, neither of
which is satisfiable. ``bats`` is not installed and the repo holds zero ``.bats``
files; and executing ``bash install.sh`` as a subprocess never reaches
``setup_parzival`` without performing a full product install, because ``main()``
calls it only after venv creation, pip install, Docker startup, health verification
and the GitHub/Jira sync steps. (Line numbers are deliberately not pinned here --
this change reflows them, and an anchor that a commit falsifies is worse than
none.) This module therefore uses the
mechanism already established across the suite: ``install_sh_no_main`` copies the
real ``install.sh`` minus its final ``main "$@"`` line and sources that copy, so
the real ``setup_parzival`` and ``configure_parzival_env`` bodies execute. The copy
is regenerated from the real file on every run and its fixture asserts the removed
line, so it cannot silently drift from the shipped installer.
"""

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
_INSTALL_SH = _SCRIPTS_DIR / "install.sh"


@pytest.fixture
def install_sh_no_main(tmp_path) -> Path:
    """Copy install.sh minus final 'main "$@"' line into tmp_path for safe sourcing."""
    content = _INSTALL_SH.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    assert lines[-1].strip() == 'main "$@"', (
        f"Expected last line 'main \"$@\"', got: {lines[-1]!r}. "
        "If install.sh structure changed, update this fixture."
    )
    copy = tmp_path / "install.sh"
    copy.write_text("".join(lines[:-1]), encoding="utf-8")
    copy.chmod(0o755)
    shutil.copy(
        _SCRIPTS_DIR / "_env_split_helpers.sh", tmp_path / "_env_split_helpers.sh"
    )
    return copy


@pytest.fixture
def dirs(tmp_path):
    """Mock INSTALL_DIR with a docker/ dir, plus an empty PROJECT_PATH."""
    install_dir = tmp_path / "install_dir"
    project_dir = tmp_path / "project_dir"
    (install_dir / "docker").mkdir(parents=True)
    project_dir.mkdir()
    return install_dir, project_dir


# Stubs for the side-effecting collaborators of setup_parzival. Defined AFTER the
# source so they override the real definitions; setup_parzival itself is real.
_STUBS = """
deploy_ai_memory_skills() { :; }
deploy_ai_memory_agents() { :; }
detect_parzival_version() { echo "none"; }
cleanup_parzival_v1() { :; }
cleanup_stale_tilde_dir() { :; }
deploy_parzival_shims() { :; }
generate_parzival_skill_shims() { :; }
deploy_oversight_templates() { :; }
sync_parzival_config_yaml() { :; }
create_agent_id_index() { :; }
setup_model_dispatch() { :; }
"""


# configure_parzival_env carries a SECOND interactive prompt ("Your name for
# Parzival greetings"), an unguarded `read` that aborts the whole installer under
# `set -e` when stdin is exhausted. That is pre-existing and out of this story's
# scope, but it makes the interactive ENABLE path undrivable in a test that must
# supply an answer with no trailing newline. This wrapper re-binds the REAL function
# under a different name and calls it with NON_INTERACTIVE forced true for the
# duration -- bash's dynamic scoping means the inner body sees the local. Nothing is
# re-typed: the real configure_parzival_env body, including the true-write, runs.
_SKIP_NAME_PROMPT = """
_cfg_src=$(declare -f configure_parzival_env)
eval "_real_configure_parzival_env${_cfg_src#configure_parzival_env}"
configure_parzival_env() { local NON_INTERACTIVE=true; _real_configure_parzival_env "$@"; }
"""


def _run_setup_parzival(
    install_sh_copy: Path,
    install_dir: Path,
    project_dir: Path,
    *,
    package_present: bool,
    non_interactive: str = "true",
    install_parzival: str | None = None,
    deploy_fails: bool = False,
    stdin: str = "",
    extra_bash: str = "",
) -> subprocess.CompletedProcess:
    """Source install.sh (no-main copy) and drive the real setup_parzival.

    ``extra_bash`` is injected after the stubs and immediately before the call, so
    it can shadow any function the real installer defines. It is how the write is
    sabotaged at a chosen point without editing the shipped script.
    """
    if package_present:
        (install_dir / "_ai-memory").mkdir(parents=True, exist_ok=True)

    install_parzival_line = (
        f'INSTALL_PARZIVAL="{install_parzival}"' if install_parzival is not None else ""
    )
    deploy_rc = 1 if deploy_fails else 0

    bash_cmd = f"""
set -euo pipefail
export INSTALL_DIR="{install_dir}"
export PROJECT_PATH="{project_dir}"
export NON_INTERACTIVE="{non_interactive}"
source "{install_sh_copy}"
INSTALL_DIR="{install_dir}"
PROJECT_PATH="{project_dir}"
NON_INTERACTIVE="{non_interactive}"
{install_parzival_line}
{_STUBS}
deploy_parzival_v2() {{ return {deploy_rc}; }}
{extra_bash}
setup_parzival
"""
    return subprocess.run(
        ["bash", "-c", bash_cmd],
        capture_output=True,
        text=True,
        input=stdin,
    )


def _env_values(install_dir: Path) -> dict[str, str]:
    """Parse the resulting docker/.env into a key -> value dict."""
    env_file = install_dir / "docker" / ".env"
    if not env_file.exists():
        return {}
    out = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def _key_order(install_dir: Path) -> list[str]:
    """Return the key names in the order they appear in docker/.env."""
    env_file = install_dir / "docker" / ".env"
    order = []
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            order.append(line.partition("=")[0].strip())
    return order


def _assert_record(env: dict[str, str], value: str, cause: str, condition: str) -> None:
    """Assert all three keys of the record together — AC-1 declares one shape."""
    assert env.get("PARZIVAL_ENABLED") == value, f"value: {env!r}"
    assert env.get("PARZIVAL_ENABLED_CAUSE") == cause, f"cause: {env!r}"
    assert env.get("PARZIVAL_ENABLED_CONDITION") == condition, f"condition: {env!r}"


class TestPackageAbsentRecordsFailed:
    """TR-1: package-absent run records cause=failed AND emits an error naming it."""

    def test_records_all_three_keys(self, install_sh_no_main, dirs):
        install_dir, project_dir = dirs
        res = _run_setup_parzival(
            install_sh_no_main, install_dir, project_dir, package_present=False
        )
        assert res.returncode == 0, res.stdout + res.stderr
        _assert_record(_env_values(install_dir), "false", "failed", "complete")

    def test_emits_machine_readable_cause_token(self, install_sh_no_main, dirs):
        """The token is the pinned observable — prose assertions pass at baseline."""
        install_dir, project_dir = dirs
        res = _run_setup_parzival(
            install_sh_no_main, install_dir, project_dir, package_present=False
        )
        combined = res.stdout + res.stderr
        assert "cause=failed" in combined, combined
        assert "[ERROR]" in combined, f"AC-1 requires an error level, got: {combined}"


class TestDeployFailureRecordsFailed:
    """TR-2: deploy_parzival_v2 non-zero -> cause=failed, token emitted, exit 0."""

    def test_records_and_emits_and_exits_zero(self, install_sh_no_main, dirs):
        install_dir, project_dir = dirs
        res = _run_setup_parzival(
            install_sh_no_main,
            install_dir,
            project_dir,
            package_present=True,
            install_parzival="true",
            deploy_fails=True,
        )
        assert res.returncode == 0, f"absence is a supported state: {res.stdout}"
        _assert_record(_env_values(install_dir), "false", "failed", "complete")
        combined = res.stdout + res.stderr
        assert "cause=failed" in combined, combined


class TestNonInteractiveRecordsOptOut:
    """TR-3: non-interactive with INSTALL_PARZIVAL unset -> opt-out, no error."""

    def test_records_opt_out_without_emitting_error(self, install_sh_no_main, dirs):
        install_dir, project_dir = dirs
        res = _run_setup_parzival(
            install_sh_no_main, install_dir, project_dir, package_present=True
        )
        assert res.returncode == 0, res.stdout + res.stderr
        _assert_record(_env_values(install_dir), "false", "opt-out", "complete")
        combined = res.stdout + res.stderr
        assert "cause=failed" not in combined, "opt-out must not emit a failure cause"
        # TR-3 requires that NO error is emitted, not merely that the failure token
        # is absent. The [ERROR] matcher exists in the sibling positive test and was
        # simply never negated here, so an opt-out path that started emitting
        # [ERROR] stayed green. Declining is not a failure.
        assert (
            "[ERROR]" not in combined
        ), f"opt-out is a supported state and must emit no error: {combined}"


class TestInteractiveDeclineRecordsOptOut:
    """TR-4: an operator who declines at the prompt records opt-out."""

    def test_decline_records_opt_out(self, install_sh_no_main, dirs):
        install_dir, project_dir = dirs
        res = _run_setup_parzival(
            install_sh_no_main,
            install_dir,
            project_dir,
            package_present=True,
            non_interactive="false",
            stdin="n\n",
        )
        assert res.returncode == 0, res.stdout + res.stderr
        _assert_record(_env_values(install_dir), "false", "opt-out", "complete")


class TestTrueWriteClearsCause:
    """TR-6: the true-write carries condition=complete and CLEARS a stale cause."""

    def test_enabled_run_writes_empty_cause_and_complete_condition(
        self, install_sh_no_main, dirs
    ):
        install_dir, project_dir = dirs
        res = _run_setup_parzival(
            install_sh_no_main,
            install_dir,
            project_dir,
            package_present=True,
            install_parzival="true",
        )
        assert res.returncode == 0, res.stdout + res.stderr
        _assert_record(_env_values(install_dir), "true", "", "complete")

    def test_successful_rerun_clears_a_stale_failed_cause(
        self, install_sh_no_main, dirs
    ):
        """Run 1 failed -> cause=failed persists; run 2 succeeds -> must be cleared.

        set_env_value can replace or append but never unset, so without an explicit
        empty-cause write the (enabled x cause=failed) cell becomes producible and
        every cause-aware consumer reports a deploy failure on a working install.
        """
        install_dir, project_dir = dirs
        env_file = install_dir / "docker" / ".env"
        env_file.write_text(
            "PARZIVAL_ENABLED=false\n"
            "PARZIVAL_ENABLED_CAUSE=failed\n"
            "PARZIVAL_ENABLED_CONDITION=complete\n",
            encoding="utf-8",
        )

        res = _run_setup_parzival(
            install_sh_no_main,
            install_dir,
            project_dir,
            package_present=True,
            install_parzival="true",
        )
        assert res.returncode == 0, res.stdout + res.stderr
        _assert_record(_env_values(install_dir), "true", "", "complete")


def _assert_no_forbidden_cell(env: dict[str, str], where: str) -> None:
    """The one invariant: no reader ever observes `enabled` AND a non-empty cause.

    AD-32 / NORMATIVE rule 2 declare that cell undefined and not producible. This
    is the actual noun. Key *order* in the file is not -- see the class docstring.
    """
    value = env.get("PARZIVAL_ENABLED")
    cause = env.get("PARZIVAL_ENABLED_CAUSE", "")
    assert not (value == "true" and cause not in ("", None)), (
        f"FORBIDDEN CELL observable {where}: "
        f"PARZIVAL_ENABLED={value!r} with PARZIVAL_ENABLED_CAUSE={cause!r}. "
        "Every cause-aware consumer reports a deploy failure on a working install."
    )


class TestForbiddenCellIsUnobservable:
    """The record is written in a single atomic pass, so the forbidden cell
    (`PARZIVAL_ENABLED=true` x non-empty cause) is UNREPRESENTABLE, not merely
    unlikely.

    This replaces an earlier guard that read file key order on a freshly *appended*
    .env and called that "the observable proxy for write order". It asserted the
    wrong noun twice over. It exercised only the append path, while every real
    re-install takes the *replace* path where file order is fixed regardless of call
    order -- so a reimplementation writing the value first passed it every time. And
    the invariant was never "keys appear in this order"; it is "no reader ever
    observes enabled with a cause attached". Ordering discipline is a property a
    future caller has to remember; atomicity is a property of the writer.

    Both tests below enter the REPLACE path by pre-seeding a docker/.env that already
    carries PARZIVAL_ENABLED=true, which is the state a re-install actually finds.
    """

    _SEEDED_ENABLED_ENV = (
        "SOME_UNRELATED_KEY=keepme\n"
        "PARZIVAL_ENABLED=true\n"
        "PARZIVAL_ENABLED_CAUSE=\n"
        "PARZIVAL_ENABLED_CONDITION=complete\n"
    )

    def test_an_interrupted_disable_never_exposes_the_cell(
        self, install_sh_no_main, dirs
    ):
        """Sabotage the write at its commit point; the file must still be coherent.

        `mv` is the single instant at which the new record becomes visible. Failing
        it models an interrupt at the worst possible moment. The target must read as
        the complete OLD record -- never as a half-applied mixture.
        """
        install_dir, project_dir = dirs
        env_file = install_dir / "docker" / ".env"
        env_file.write_text(self._SEEDED_ENABLED_ENV, encoding="utf-8")

        res = _run_setup_parzival(
            install_sh_no_main,
            install_dir,
            project_dir,
            package_present=False,
            # Fail WITHOUT performing the move — the point is that the commit never
            # lands, not that it lands and reports failure.
            extra_bash="mv() { return 1; }\n",
        )
        env = _env_values(install_dir)
        _assert_no_forbidden_cell(env, "after an interrupted disable (mv sabotaged)")
        assert (
            env.get("SOME_UNRELATED_KEY") == "keepme"
        ), f"an aborted record write must not damage unrelated keys: {env!r}"
        # The previous record survives intact rather than being half-applied.
        _assert_record(env, "true", "", "complete")
        # Absence is a supported operating state: a failed record write is reported
        # at error level and does NOT abort the install. Emitting an error and
        # changing the exit code are separable and AC-1 requires only the first.
        assert res.returncode == 0, res.stdout + res.stderr
        combined = res.stdout + res.stderr
        assert "Could not commit the Parzival enablement record" in combined, combined

    def test_the_detector_fires_against_a_sequential_writer(
        self, install_sh_no_main, dirs
    ):
        """POSITIVE CONTROL — a detector never observed failing is a hope (SO-15).

        This injects the previous sequential implementation (cause first, value
        last) and interrupts it between the two writes. On a .env already carrying
        PARZIVAL_ENABLED=true that ordering transits the forbidden cell with no
        interrupt strictly required, and the snapshot proves the assertion above is
        one that CAN fail. If this test ever passes without raising, the detector has
        stopped detecting.
        """
        install_dir, project_dir = dirs
        env_file = install_dir / "docker" / ".env"
        env_file.write_text(self._SEEDED_ENABLED_ENV, encoding="utf-8")

        sabotage = (
            "set_parzival_enablement() {\n"
            '    set_env_value "PARZIVAL_ENABLED_CAUSE" "$2"\n'
            "    return 1\n"
            "}\n"
        )
        _run_setup_parzival(
            install_sh_no_main,
            install_dir,
            project_dir,
            package_present=False,
            extra_bash=sabotage,
        )
        env = _env_values(install_dir)
        with pytest.raises(AssertionError, match="FORBIDDEN CELL"):
            _assert_no_forbidden_cell(env, "sequential writer (positive control)")

    def test_a_completed_disable_replaces_the_whole_record(
        self, install_sh_no_main, dirs
    ):
        """The un-sabotaged replace path: old record fully superseded, one line each."""
        install_dir, project_dir = dirs
        env_file = install_dir / "docker" / ".env"
        env_file.write_text(self._SEEDED_ENABLED_ENV, encoding="utf-8")

        res = _run_setup_parzival(
            install_sh_no_main, install_dir, project_dir, package_present=False
        )
        assert res.returncode == 0, res.stdout + res.stderr
        env = _env_values(install_dir)
        _assert_record(env, "false", "failed", "complete")
        _assert_no_forbidden_cell(env, "after a completed disable")
        assert env.get("SOME_UNRELATED_KEY") == "keepme", env

        # Exactly one line per key. Shell reads the first duplicate and
        # python-dotenv reads the last, so a duplicate is a reader-disagreement bug.
        order = _key_order(install_dir)
        for key in (
            "PARZIVAL_ENABLED",
            "PARZIVAL_ENABLED_CAUSE",
            "PARZIVAL_ENABLED_CONDITION",
        ):
            assert order.count(key) == 1, f"{key} duplicated: {order}"


class TestAnAnswerIsNeverDiscarded:
    """`read` returns non-zero on EOF EVEN WHEN IT POPULATED THE VARIABLE.

    ``printf 'y' | ./install.sh``, a heredoc with no trailing newline and an expect
    driver all deliver a real answer with no final newline. Testing the return code
    alone therefore threw the operator's ``y`` away and recorded a decline — a
    regression introduced when the EOF guard was added, and the only finding in its
    review round that *loses an operator's answer* rather than misreporting state.
    The suite had no such case, which is why it shipped.
    """

    def test_y_without_a_trailing_newline_still_enables(self, install_sh_no_main, dirs):
        install_dir, project_dir = dirs
        res = _run_setup_parzival(
            install_sh_no_main,
            install_dir,
            project_dir,
            package_present=True,
            non_interactive="false",
            stdin="y",  # NO trailing newline — this is the whole point
            extra_bash=_SKIP_NAME_PROMPT,
        )
        assert res.returncode == 0, res.stdout + res.stderr
        _assert_record(_env_values(install_dir), "true", "", "complete")

    def test_y_with_a_trailing_newline_still_enables(self, install_sh_no_main, dirs):
        """Positive control: the normal path must not have been broken by the fix."""
        install_dir, project_dir = dirs
        res = _run_setup_parzival(
            install_sh_no_main,
            install_dir,
            project_dir,
            package_present=True,
            non_interactive="false",
            stdin="y\n",
            extra_bash=_SKIP_NAME_PROMPT,
        )
        assert res.returncode == 0, res.stdout + res.stderr
        _assert_record(_env_values(install_dir), "true", "", "complete")


class TestGenuineEofLeavesTheRecordAlone:
    """A closed stdin writes NOTHING to the record.

    Three reasons, in increasing severity: a cause is a claim about operator intent
    and a closed stdin supports none; writing an empty cause DESTROYS a `cause=failed`
    recorded by an earlier run; and because `setup_parzival` never reads the existing
    PARZIVAL_ENABLED before prompting, writing `false` here DISABLES A DEPLOYED,
    WORKING PARZIVAL because nobody answered a prompt.

    Writing nothing must NOT mean saying nothing: `DEC-PM441-D3` attaches a
    visibility condition to the OFFERS ruling — the product never lets a disabled
    state be silent. The announcement is asserted separately below so "quiet" cannot
    pass for "correct".
    """

    def test_the_eof_path_still_announces(self, install_sh_no_main, dirs):
        install_dir, project_dir = dirs
        res = _run_setup_parzival(
            install_sh_no_main,
            install_dir,
            project_dir,
            package_present=True,
            non_interactive="false",
            stdin="",
        )
        assert res.returncode == 0, res.stdout + res.stderr
        combined = res.stdout + res.stderr
        assert "EOF" in combined, combined
        assert "left unchanged" in combined, (
            "the EOF path must say that it wrote nothing — a silent skip is exactly "
            f"what DEC-PM441-D3's visibility condition forbids:\n{combined}"
        )

    def test_eof_does_not_disable_a_working_install(self, install_sh_no_main, dirs):
        install_dir, project_dir = dirs
        env_file = install_dir / "docker" / ".env"
        env_file.write_text(
            "PARZIVAL_ENABLED=true\n"
            "PARZIVAL_ENABLED_CAUSE=\n"
            "PARZIVAL_ENABLED_CONDITION=complete\n",
            encoding="utf-8",
        )
        res = _run_setup_parzival(
            install_sh_no_main,
            install_dir,
            project_dir,
            package_present=True,
            non_interactive="false",
            stdin="",  # closed stdin, nothing typed
        )
        assert res.returncode == 0, res.stdout + res.stderr
        _assert_record(_env_values(install_dir), "true", "", "complete")

    def test_eof_does_not_overwrite_a_recorded_failure(self, install_sh_no_main, dirs):
        install_dir, project_dir = dirs
        env_file = install_dir / "docker" / ".env"
        env_file.write_text(
            "PARZIVAL_ENABLED=false\n"
            "PARZIVAL_ENABLED_CAUSE=failed\n"
            "PARZIVAL_ENABLED_CONDITION=complete\n",
            encoding="utf-8",
        )
        res = _run_setup_parzival(
            install_sh_no_main,
            install_dir,
            project_dir,
            package_present=True,
            non_interactive="false",
            stdin="",
        )
        assert res.returncode == 0, res.stdout + res.stderr
        _assert_record(_env_values(install_dir), "false", "failed", "complete")


class TestTheWriterMatchesEveryFormPythonDotenvAccepts:
    """`export KEY=` and indented keys were not matched, so a DUPLICATE was appended.

    python-dotenv accepts `export PARZIVAL_ENABLED=true`; an anchored
    /^PARZIVAL_ENABLED=/ does not match it, so the END block appended a second
    definition. The result was one file carrying `export PARZIVAL_ENABLED=true` AND
    `PARZIVAL_ENABLED=false` — the two readers disagreeing inside one file, which is
    the forbidden cell reached by transport rather than by interrupt. The function's
    documented duplicate-collapsing property held only for exactly-anchored lines.
    """

    @pytest.mark.parametrize(
        "seed_line",
        [
            "export PARZIVAL_ENABLED=true",
            "  PARZIVAL_ENABLED=true",
            "\tPARZIVAL_ENABLED=true",
            "export PARZIVAL_ENABLED_CAUSE=failed",
        ],
        ids=["export", "indent-spaces", "indent-tab", "export-cause"],
    )
    def test_no_duplicate_definition_survives(
        self, install_sh_no_main, dirs, seed_line
    ):
        install_dir, project_dir = dirs
        env_file = install_dir / "docker" / ".env"
        env_file.write_text(f"{seed_line}\nOTHER=1\n", encoding="utf-8")

        res = _run_setup_parzival(
            install_sh_no_main,
            install_dir,
            project_dir,
            package_present=False,  # package absent -> false / failed / complete
        )
        assert res.returncode == 0, res.stdout + res.stderr

        body = env_file.read_text(encoding="utf-8")
        for key in (
            "PARZIVAL_ENABLED",
            "PARZIVAL_ENABLED_CAUSE",
            "PARZIVAL_ENABLED_CONDITION",
        ):
            hits = re.findall(rf"^[ \t]*(?:export[ \t]+)?{key}=", body, re.M)
            assert len(hits) == 1, (
                f"{key} has {len(hits)} definitions after the write; a duplicate "
                f"makes shell and python-dotenv disagree inside one file:\n{body}"
            )
        _assert_record(_env_values(install_dir), "false", "failed", "complete")
        assert "OTHER=1" in body, "unrelated keys must survive the rewrite"


class TestAnUnwritableRecordDoesNotKillTheInstaller:
    """`[[ -f ... ]] || touch` was the one unguarded failure path in the writer.

    `set -euo pipefail` is global and `setup_parzival` is called bare, so an
    unwritable docker/ turned "Parzival is off" into "the installer died" — the exact
    outcome the function's own contract forbids three lines above it.
    """

    @pytest.mark.skipif(
        hasattr(os, "geteuid") and os.geteuid() == 0,
        reason="chmod(0o500) does not constrain root — as root the directory stays "
        "writable, docker/.env is created, the guard under test never fires, and "
        "the test would pass while asserting nothing",
    )
    def test_an_unwritable_docker_dir_still_returns_zero(
        self, install_sh_no_main, dirs
    ):
        install_dir, project_dir = dirs
        docker_dir = install_dir / "docker"
        original_mode = docker_dir.stat().st_mode
        docker_dir.chmod(0o500)  # r-x: cannot create docker/.env
        try:
            res = _run_setup_parzival(
                install_sh_no_main,
                install_dir,
                project_dir,
                package_present=False,
            )
        finally:
            docker_dir.chmod(original_mode)

        assert res.returncode == 0, (
            "an unwritable docker/ must not abort the install:\n"
            + res.stdout
            + res.stderr
        )
        combined = res.stdout + res.stderr
        # THE GUARD'S OWN TEXT, not "cause=failed". This fixture runs with
        # package_present=False, and that path logs "Parzival V2 package not found
        # in source repo — skipping Parzival setup (cause=failed)" BEFORE it calls
        # set_parzival_enablement "false" "failed". So `"cause=failed" in combined`
        # is satisfied by the earlier message whether or not the touch guard under
        # test ever fires — it asserted the fixture, not the fix. "record NOT
        # written" is emitted only by the guard itself.
        assert "record NOT written" in combined, combined


class TestTheRecordCommitPreservesTheFilesMode:
    """The mktemp+rename commit must not publish the temp file's own permissions.

    ``set_parzival_enablement`` builds the new record in a ``mktemp`` file — 0600 by
    default — and renames it over ``docker/.env``. Without the mode transfer that
    rename silently republishes 0600 in place of the file's real mode, which is a
    likelier everyday breakage than the torn write the rename exists to prevent.
    Nothing in the suite asserted it.
    """

    def _write_record(self, install_sh_no_main: Path, install_dir: Path):
        return subprocess.run(
            [
                "bash",
                "-c",
                "set -uo pipefail\n"
                f'export INSTALL_DIR="{install_dir}"\n'
                f'source "{install_sh_no_main}"\n'
                f'INSTALL_DIR="{install_dir}"\n'
                'set_parzival_enablement "true" ""\n',
            ],
            capture_output=True,
            text=True,
        )

    def test_the_env_files_mode_survives_the_record_write(
        self, install_sh_no_main, dirs
    ):
        install_dir, _ = dirs
        env_file = install_dir / "docker" / ".env"
        env_file.write_text("PARZIVAL_ENABLED=false\n", encoding="utf-8")
        env_file.chmod(0o640)

        res = self._write_record(install_sh_no_main, install_dir)
        assert res.returncode == 0, res.stdout + res.stderr

        # Positive control on the fixture itself: if the write did not happen, the
        # mode assertion below would hold trivially on an untouched file.
        assert "PARZIVAL_ENABLED=true" in env_file.read_text(encoding="utf-8"), (
            "the record was not rewritten, so the mode assertion would be vacuous:\n"
            + res.stdout
            + res.stderr
        )
        actual = stat.S_IMODE(env_file.stat().st_mode)
        assert actual == 0o640, (
            "the record was committed through a mktemp file and the rename "
            f"published its own permissions over docker/.env: {oct(actual)} != 0o640"
        )

    # OWNERSHIP IS DELIBERATELY NOT ASSERTED, and this is a stated residual rather
    # than an oversight. Proving the chown round-trips requires a second uid/gid to
    # chown *to*, which an unprivileged test process does not have; asserting that
    # the owner is unchanged would pass identically whether or not the chown ran at
    # all, which is a test that cannot fail. Owner preservation therefore remains
    # verified by code-reading only. Closing it needs a privileged harness, which is
    # more machinery than the line it would guard.
