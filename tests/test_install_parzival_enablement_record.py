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


def _permission_warning_phrases(env_file) -> dict:
    """The distinctive phrase each of the four permission-transfer cells logs.

    FULL phrases, deliberately not loose substrings. Three of these four strings
    share the token ``mode`` or the token ``Could not read``, so a test matching
    those two independently cannot tell one cell from another -- which is exactly
    what happened to the mode-read assertion the moment the other three cells
    gained messages of their own. Keyed by cell so a failure names the cell.
    """
    return {
        "owner-read": f"Could not read {env_file} ownership —",
        "owner-apply": f"Could not apply {env_file} ownership —",
        "mode-read": f"Could not read {env_file} mode —",
        "mode-apply": f"Could not apply {env_file} mode —",
    }


def _bsd_stat_reads_a_mode() -> bool:
    """True where ``stat -f '%Lp'`` really is the BSD format flag (macOS).

    Asked of the platform rather than inferred from ``sys.platform``, because what
    the installer's fallback depends on is this exact invocation's behaviour. On GNU
    ``-f`` is ``--file-system``, so this returns False and the warning arm is
    reachable; on BSD it yields the octal mode, the chmod succeeds and the arm is not.
    """
    try:
        res = subprocess.run(
            ["stat", "-f", "%Lp", str(_INSTALL_SH)], capture_output=True, text=True
        )
    except OSError:  # no stat on PATH at all
        return False
    return re.fullmatch(r"[0-7]{1,4}", res.stdout.strip()) is not None


def _bsd_stat_reads_an_owner() -> bool:
    """True where ``stat -f '%u:%g'`` really is the BSD format flag (macOS).

    A SEPARATE probe from the mode one above, and deliberately so: it asks the
    owner cell's own question. The owner test was gated on
    ``_bsd_stat_reads_a_mode()`` while its ``reason=`` asserted that the OWNER
    fallback succeeds -- but a ``%Lp`` probe establishes only that the MODE
    fallback succeeds. A closed descriptor and a dead reader are different
    experiments, and so are these.

    The two co-vary on every platform in use today (on BSD both ``-f`` forms are
    format strings, on GNU ``-f`` is ``--file-system`` and neither is), which is
    precisely what makes the substitution invisible: the gate returns the right
    answer for the wrong reason, and would keep doing so until some platform
    supported one format and not the other. Mirrors install.sh's owner regex
    ``^[0-9]+:[0-9]+$`` the way the mode probe mirrors ``^[0-7]{1,4}$``.
    """
    try:
        res = subprocess.run(
            ["stat", "-f", "%u:%g", str(_INSTALL_SH)], capture_output=True, text=True
        )
    except OSError:  # no stat on PATH at all
        return False
    return re.fullmatch(r"[0-9]+:[0-9]+", res.stdout.strip()) is not None


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
        "writable, docker/.env is created and the guard under test never fires, so "
        "the assertion below finds no guard message and the test FAILS on a healthy "
        "installer. The skip exists to avoid that false red, not a vacuous green: "
        "the earlier `cause=failed` assertion was the vacuous one, and this hunk "
        "replaced it",
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
        # test ever fires — it asserted the fixture, not the fix.
        #
        # AND "record NOT written" IS NOT THAT TEXT EITHER. Two guards inside
        # set_parzival_enablement emit it — the `touch` guard and the `mktemp`
        # guard — so it confirms that *a* guard fired, not *which*, while this
        # test's whole subject is the touch guard. (The third, the awk guard,
        # writes "record — NOT written" and does not match.) The touch guard is
        # the only one whose message puts the env-file path directly after
        # "Could not create"; the mktemp guard says "a temp file beside" first.
        env_file = install_dir / "docker" / ".env"
        assert f"Could not create {env_file} —" in combined, combined


class TestTheRecordCommitPreservesTheFilesMode:
    """The mktemp+rename commit must not publish the temp file's own permissions.

    ``set_parzival_enablement`` builds the new record in a ``mktemp`` file — 0600 by
    default — and renames it over ``docker/.env``. Without the mode transfer that
    rename silently republishes 0600 in place of the file's real mode, which is a
    likelier everyday breakage than the torn write the rename exists to prevent.
    Nothing in the suite asserted it.

    OWNERSHIP IS DELIBERATELY NOT ASSERTED, and this is a stated residual rather
    than an oversight. Proving the chown round-trips requires a second uid/gid to
    chown *to*, which an unprivileged test process does not have; asserting that the
    owner is unchanged would pass identically whether or not the chown ran at all,
    which is a test that cannot fail. Owner preservation therefore remains verified
    by code-reading only. Closing it needs a privileged harness, which is more
    machinery than the line it would guard. Stated here, in the docstring, so it is
    visible to ``--collect-only`` and to anything else that reads docstrings — a
    trailing ``#`` comment records the same honesty where no tool will surface it.
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


class TestAnUnreadableModeIsAnnouncedRatherThanSwallowed:
    """The mode transfer must be LOUD when it cannot happen — item 12's whole point.

    Without this the branch was dead to the suite, and a branch dead to the suite is
    where the round-4 defect lived: the guard read ``[[ -n "$_pe_mode" ]]``, which on
    GNU is **true on garbage**. ``stat -f`` is ``--file-system`` on GNU, not a format
    flag, so when the primary ``stat -c`` fails the fallback prints a multi-line
    filesystem block to stdout, the command substitution captures it, the emptiness
    test passes, ``chmod`` is handed that block and fails into ``2>/dev/null || true``,
    and the rename publishes mktemp's 0600 over docker/.env — silently, which is
    exactly the breakage the branch exists to announce. Measured on GNU coreutils 9.4:
    332 bytes captured, 0644 in, 0600 out, nothing logged.

    So this test drives the real function with **only the primary ``stat`` stubbed
    out**; the fallback runs the real system ``stat``, and the value under test is
    what this platform genuinely produces on that path rather than an imitation of it.
    """

    def _write_record_with_a_failing_primary_stat(
        self, install_sh_no_main: Path, install_dir: Path
    ):
        return subprocess.run(
            [
                "bash",
                "-c",
                "set -uo pipefail\n"
                f'export INSTALL_DIR="{install_dir}"\n'
                f'source "{install_sh_no_main}"\n'
                f'INSTALL_DIR="{install_dir}"\n'
                # Shadows the builtin lookup for the sourced function only.
                'stat() { if [[ "$1" == "-c" ]]; then return 1; fi; '
                'command stat "$@"; }\n'
                'set_parzival_enablement "true" ""\n',
            ],
            capture_output=True,
            text=True,
        )

    @pytest.mark.skipif(
        _bsd_stat_reads_a_mode(),
        reason="on a platform where `stat -f '%Lp'` really is the BSD format flag "
        "the fallback SUCCEEDS and returns a usable mode, so the chmod runs and the "
        "warning arm is correctly not reached — the branch under test is only "
        "reachable where that fallback cannot produce a mode",
    )
    def test_an_unreadable_mode_warns_and_still_writes_the_record(
        self, install_sh_no_main, dirs
    ):
        install_dir, _ = dirs
        env_file = install_dir / "docker" / ".env"
        env_file.write_text("PARZIVAL_ENABLED=false\n", encoding="utf-8")
        env_file.chmod(0o640)

        res = self._write_record_with_a_failing_primary_stat(
            install_sh_no_main, install_dir
        )
        combined = res.stdout + res.stderr

        # The contract item 12 states for this arm, all three halves of it: the
        # operator is told, the record is still written, and the install proceeds.
        # Matched as ONE full phrase. This previously tested "Could not read" and
        # "mode" as two independent substrings, which stopped identifying this cell
        # once the other three permission cells gained messages: the owner-read
        # warning also fires on this path and also begins "Could not read", so the
        # loose form passes on a run where the mode-read arm never spoke at all.
        assert _permission_warning_phrases(env_file)["mode-read"] in combined, (
            "the mode could not be read and nothing said so — reproducing the "
            f"breakage without a word is the failure mode:\n{combined}"
        )
        assert res.returncode == 0, (
            "a warning is not a failure; the install must still proceed:\n" + combined
        )
        assert "PARZIVAL_ENABLED=true" in env_file.read_text(encoding="utf-8"), (
            "the record must still be committed — the warning reports a degraded "
            f"permission transfer, not an abandoned write:\n{combined}"
        )
        # The OTHER half of this commit's central claim, asserted by nobody until
        # now: the test seeded 0640 and never re-read the mode, so "0644 in, 0600
        # out" -- the breakage the warning exists to announce -- went unverified.
        # The warning does not repair the transfer; it reports it, and what it
        # reports must actually be true or the message is the only evidence and it
        # is unchecked. mktemp creates at 0600, so that is what the rename commits.
        degraded = stat.S_IMODE(env_file.stat().st_mode)
        assert degraded == 0o600, (
            "the warning fired but the mode it describes did not actually degrade "
            f"to mktemp's 0600: {oct(degraded)} — the message would be reporting "
            "something that did not happen"
        )


class TestEveryPermissionTransferCellAnnouncesItsOwnFailure:
    """All FOUR permission-transfer cells warn, not just the one that already did.

    The transfer has four cells -- read the owner, apply the owner, read the mode,
    apply the mode -- and only mode-read spoke. The other three ended in
    ``2>/dev/null || true``, which discards the diagnostic and the exit status
    together, so the rename committed mktemp's 0600/owner over docker/.env with
    nothing logged. Two independent root causes produced that, and fixing either
    alone leaves the other standing:

    (a) A syscall can fail on a value that is perfectly VALID. Both apply-cells
        reach their syscall only after the regex has accepted the captured value,
        so the regex cannot be what protects them -- ``chown``/``chmod`` can still
        be refused by the kernel (read-only mount, unmapped uid under userns, an
        immutable attribute) with the value entirely well-formed. These two tests
        stub the syscall rather than corrupt the value, because corrupting the
        value would exercise the regex, not the cell.

    (b) The owner cell had no branch AT ALL -- it was ``[[ regex ]] && chown ... ||
        true``, one line, in which a rejected capture and a failed chown are the
        same silent outcome. That omission PREDATES this round entirely; it is not
        a regression introduced alongside the mode cell's guard.

    The negative control below is the test that makes the other three mean
    something. Its own non-vacuity is established by them: they assert these exact
    phrases PRESENT, from the same ``_permission_warning_phrases`` dict, so the
    phrases are demonstrably matchable and their absence here is a real
    observation rather than a typo that can never match anything.

    THAT BACKING IS PER-CELL AND PER-PLATFORM, which the sentence above used to
    hide. The negative control asserts four absences; each is only as meaningful
    as the test that proves its phrase can appear:

    * ``owner-apply`` / ``mode-apply`` -- backed unconditionally. Both firing
      tests stub a syscall, which every platform can do, so neither is gated.
    * ``owner-read`` -- backed by ``test_an_unreadable_owner_is_announced``,
      which SKIPS where ``stat -f '%u:%g'`` is a real format flag.
    * ``mode-read`` -- backed by ``test_an_unreadable_mode_warns_and_still_
      writes_the_record`` in the class above, which SKIPS where ``stat -f
      '%Lp'`` is a real format flag.

    So on GNU (where the suite runs, and where both ``-f`` probes fail) all four
    absences are backed by an executing test. On BSD the two read-arms are not,
    and their absence assertions hold trivially there. That is a real limit of
    this control on that platform, recorded rather than papered over -- the arms
    skip because the installer's fallback genuinely succeeds there, so the
    warning correctly never fires and there is no defect hiding behind them.
    """

    def _write_record(self, install_sh_no_main: Path, install_dir: Path, prelude=""):
        """Drive the real function, optionally shadowing a collaborator first.

        The prelude is injected AFTER the source, so a function defined there
        overrides the real command lookup for the sourced body only.
        """
        return subprocess.run(
            [
                "bash",
                "-c",
                "set -uo pipefail\n"
                f'export INSTALL_DIR="{install_dir}"\n'
                f'source "{install_sh_no_main}"\n'
                f'INSTALL_DIR="{install_dir}"\n'
                f"{prelude}"
                'set_parzival_enablement "true" ""\n',
            ],
            capture_output=True,
            text=True,
        )

    def _seed(self, install_dir: Path) -> Path:
        env_file = install_dir / "docker" / ".env"
        env_file.write_text("PARZIVAL_ENABLED=false\n", encoding="utf-8")
        env_file.chmod(0o640)
        return env_file

    def _assert_record_still_written(self, env_file: Path, res, combined: str):
        """Every cell is best-effort: it degrades the transfer, never the write."""
        assert res.returncode == 0, (
            "a warning is not a failure; the install must still proceed:\n" + combined
        )
        assert "PARZIVAL_ENABLED=true" in env_file.read_text(encoding="utf-8"), (
            "the record must still be committed — the warning reports a degraded "
            f"permission transfer, not an abandoned write:\n{combined}"
        )

    @pytest.mark.skipif(
        _bsd_stat_reads_an_owner(),
        reason="on a platform where `stat -f '%u:%g'` really is the BSD format "
        "flag the OWNER fallback SUCCEEDS and returns a usable owner:group, so "
        "the chown runs and the read arm is correctly not reached — the branch "
        "under test is only reachable where that fallback cannot produce an owner",
    )
    def test_an_unreadable_owner_is_announced(self, install_sh_no_main, dirs):
        install_dir, _ = dirs
        env_file = self._seed(install_dir)

        # Only the PRIMARY stat is stubbed; the fallback runs the real system stat,
        # so the captured value is what this platform genuinely produces on that
        # path rather than an imitation of it.
        res = self._write_record(
            install_sh_no_main,
            install_dir,
            'stat() { if [[ "$1" == "-c" ]]; then return 1; fi; command stat "$@"; }\n',
        )
        combined = res.stdout + res.stderr
        phrases = _permission_warning_phrases(env_file)

        assert phrases["owner-read"] in combined, (
            "the owner could not be read and nothing said so — the rename then "
            f"commits the temp file's owner in silence:\n{combined}"
        )
        self._assert_record_still_written(env_file, res, combined)

    def test_an_unappliable_owner_is_announced(self, install_sh_no_main, dirs):
        install_dir, _ = dirs
        env_file = self._seed(install_dir)

        # The value is VALID and the regex accepts it: this drives root cause (a),
        # the syscall refusing a well-formed value. Asserting the read-cell stayed
        # quiet is what proves the apply-cell -- not the read-cell -- spoke.
        res = self._write_record(
            install_sh_no_main, install_dir, "chown() { return 1; }\n"
        )
        combined = res.stdout + res.stderr
        phrases = _permission_warning_phrases(env_file)

        assert phrases["owner-apply"] in combined, (
            "chown failed on a valid owner and nothing said so:\n" + combined
        )
        assert phrases["owner-read"] not in combined, (
            "the owner READ succeeded here; a read-failure warning means the two "
            f"cells are not distinguishable:\n{combined}"
        )
        self._assert_record_still_written(env_file, res, combined)

    def test_an_unappliable_mode_is_announced(self, install_sh_no_main, dirs):
        install_dir, _ = dirs
        env_file = self._seed(install_dir)

        res = self._write_record(
            install_sh_no_main, install_dir, "chmod() { return 1; }\n"
        )
        combined = res.stdout + res.stderr
        phrases = _permission_warning_phrases(env_file)

        assert phrases["mode-apply"] in combined, (
            "chmod failed on a valid mode and nothing said so — this is the cell "
            f"whose silence published 0600 over docker/.env:\n{combined}"
        )
        assert phrases["mode-read"] not in combined, (
            "the mode READ succeeded here; a read-failure warning means the two "
            f"cells are not distinguishable:\n{combined}"
        )
        self._assert_record_still_written(env_file, res, combined)
        # The message claims the record "keeps the temporary file's default
        # permissions". Asserted by nobody until now on THIS arm, though its
        # sibling in the class above has carried the equivalent check since the
        # 0600 assertion was added: the message was the only evidence that the
        # transfer degraded, and an unchecked message is a claim, not a result.
        # chmod is stubbed to fail, so the seeded 0640 is never applied and the
        # rename commits mktemp's 0600 -- the same end state the unreadable-mode
        # arm produces, reached through the apply cell instead of the read cell.
        degraded = stat.S_IMODE(env_file.stat().st_mode)
        assert degraded == 0o600, (
            "the warning fired but the mode it describes did not actually degrade "
            f"to mktemp's 0600: {oct(degraded)} — the message would be reporting "
            "something that did not happen"
        )

    def test_a_healthy_install_says_none_of_the_four(self, install_sh_no_main, dirs):
        """NEGATIVE CONTROL — the direction a warning test cannot check itself.

        The three tests above prove each cell CAN warn. None of them can tell a
        correct guard from one inverted to warn unconditionally: that mutant emits
        every message on every run and passes all three. Only asserting silence on
        a healthy install separates them, which is why this is not decoration.

        It is also the arm that must not regress into noise. These warnings fire on
        the ordinary success path of every install if the condition is written
        backwards, and an installer that cries permission failure on a healthy run
        trains operators to ignore the one run where it is real.
        """
        install_dir, _ = dirs
        env_file = self._seed(install_dir)

        res = self._write_record(install_sh_no_main, install_dir)
        combined = res.stdout + res.stderr

        # Positive control on the fixture: without this, a run that never reached
        # the transfer at all would satisfy every absence assertion below.
        assert "PARZIVAL_ENABLED=true" in env_file.read_text(encoding="utf-8"), (
            "the record was not written, so the silence below is vacuous:\n" + combined
        )
        for cell, phrase in _permission_warning_phrases(env_file).items():
            assert phrase not in combined, (
                f"the {cell} cell warned on a HEALTHY install — the guard is "
                f"inverted, and a warning that always fires is not a warning:\n"
                f"{combined}"
            )
        assert res.returncode == 0, combined


class TestALogWriteCannotKillTheInstall:
    """A broken stdout must not stop the record from being committed.

    ``set -euo pipefail`` is global in install.sh and ``main`` redirects stdout
    into ``tee`` via ``exec > >(tee -a "$INSTALL_LOG") 2>&1``. Both are anchored
    here by quoted line rather than by line number: the change under test shifted
    those numbers by 24, and the first draft of this docstring cited two that were
    already stale.

    So all five ``log_*`` functions run with their stdout owned by another
    process, and each was a bare ``echo -e``. A bare ``echo`` that cannot write
    returns nonzero, errexit sees a failed simple command, and the installer dies
    -- so the LOGGER decides whether the record gets written. That is the
    inversion under test: logging is meant to describe the install, not to be
    able to end it.

    This drives the real ``set_parzival_enablement`` behind a real ``log_*`` call
    with stdout genuinely closed, rather than stubbing the logger -- a stubbed
    logger cannot fail, which is the only interesting property here.

    WHAT THIS PINS, AND WHAT IT DOES NOT. The guard is ``|| true``, an errexit
    suppressor, so it covers a write that fails AND RETURNS: a closed descriptor
    (EBADF, exercised here), ENOSPC, EIO. It does NOT cover SIGPIPE -- a dead
    reader on the other end of the pipe has the kernel kill the shell outright
    (measured: signal 13, record not committed, identically with and without the
    guard), and no ``||`` clause runs after a signal. There is deliberately no
    test asserting the SIGPIPE outcome: it is an open gap, and a test asserting
    the current behaviour would enshrine it as intended. Closing it needs
    ``trap '' PIPE`` at script scope, which is a signal-disposition change for
    the whole installer and not this change's to make.

    🔴 WHAT THIS TEST ACTUALLY DRIVES, SAID PLAINLY BECAUSE IT IS NOT THE
    PRODUCTION TRIGGER. The mechanism here is ``exec 1>&-`` -- EBADF, a descriptor
    closed by the test itself. **No site in install.sh can produce that
    condition**; nothing in the installer closes its own stdout. The real
    production breakage is install.sh's ``tee`` dying, and that arrives as one of
    two different events: a write that fails and RETURNS (ENOSPC on the log
    filesystem, EIO), which is what the guard covers and what EBADF stands in for
    here; or SIGPIPE on a closed read end, which the guard does NOT cover and no
    case below asserts.

    So this is a PROXY for the covered class, chosen because it is the only
    member of that class a test can raise deterministically without filling a
    disk. It is honest about the guard's mechanism -- errexit suppression on a
    non-zero return -- and it is silent about the trigger frequency. Read it as
    "the guard suppresses a returning write failure", never as "the tee case is
    covered".
    """

    def test_a_closed_stdout_really_does_fail_a_write(self):
        """Non-vacuity control — without this the test below proves nothing.

        If ``echo`` to a closed descriptor returned 0 on this platform, then no
        write ever fails, errexit never fires, and the guarded test would pass
        just as happily against the unguarded ``echo -e``. Establish that the
        hazard is real here before asserting it is handled.
        """
        res = subprocess.run(
            ["bash", "-c", 'exec 1>&-; echo hi; echo "rc=$?" >&2'],
            capture_output=True,
            text=True,
        )
        assert "rc=1" in res.stderr, (
            "a write to a closed stdout did not fail on this platform, so the "
            f"guard below is guarding nothing that can happen here:\n{res.stderr}"
        )

    # ONE CASE PER GUARDED FUNCTION -- five functions, five parametrised cases,
    # and that count is the point of this parametrisation rather than an
    # accident of style. The previous revision of this class drove `log_info`
    # and nothing else: `log_info` appeared once in this module and the other
    # four `log_*` names zero times, so FOUR of the five `|| true` guards could
    # be deleted outright with the whole suite still green. A guard no test can
    # remove is a guard no test is holding.
    #
    # `log_debug` carries `LOG_LEVEL=debug` because its `echo` is wrapped in an
    # `[[ "$LOG_LEVEL" == "debug" ]]` branch. At the default level the echo never
    # executes, so the case would pass identically against the unguarded body --
    # green, and proving nothing. The level is exported BEFORE `source` because
    # install.sh binds `LOG_LEVEL="${LOG_LEVEL:-info}"` at source time.
    @pytest.mark.parametrize(
        "log_fn,log_level",
        [
            ("log_info", None),
            ("log_success", None),
            ("log_warning", None),
            ("log_error", None),
            ("log_debug", "debug"),
        ],
    )
    def test_the_record_is_committed_even_when_logging_cannot_write(
        self, install_sh_no_main, dirs, log_fn, log_level
    ):
        install_dir, _ = dirs
        env_file = install_dir / "docker" / ".env"
        env_file.write_text("PARZIVAL_ENABLED=false\n", encoding="utf-8")

        level = f'export LOG_LEVEL="{log_level}"\n' if log_level else ""
        res = subprocess.run(
            [
                "bash",
                "-c",
                # -e deliberately included: it is the real global setting, and
                # the whole defect only exists under errexit.
                "set -euo pipefail\n"
                f'export INSTALL_DIR="{install_dir}"\n'
                f"{level}"
                f'source "{install_sh_no_main}"\n'
                f'INSTALL_DIR="{install_dir}"\n'
                # stdout is gone from here on, exactly as it is when the process
                # on the other end of install.sh's `tee` redirect has died.
                "exec 1>&-\n"
                f'{log_fn} "the installer logs before it commits the record"\n'
                f'set_parzival_enablement "true" "" "complete" "{env_file}"\n',
            ],
            capture_output=True,
            text=True,
        )

        assert res.returncode == 0, (
            f"a failed {log_fn} write ended the run — the record was never "
            "reached. errexit fires AT the echo, so a `return 0` on the "
            "following line does not help; the echo itself must not report "
            f"failure:\n{res.stderr}"
        )
        assert "PARZIVAL_ENABLED=true" in env_file.read_text(encoding="utf-8"), (
            f"the enablement record was not committed because a {log_fn} line "
            f"could not be written:\n{res.stderr}"
        )


class TestARecordFailureIsCountedAndGated:
    """A record write that fails must not be able to exit 0 in silence.

    ``set_parzival_enablement`` ALWAYS returns 0 -- deliberately, and that
    fail-open contract is unchanged. Its four write-failure branches therefore
    announced themselves through ``log_error`` and through nothing else. Once the
    five ``log_*`` functions became ``|| true``-guarded (the class above), that
    single channel became DROPPABLE: ``main`` runs with
    ``exec > >(tee -a "$INSTALL_LOG") 2>&1`` so stderr is not a fallback, and a
    dead reader lets all four branches reach ``return 0`` with the message
    undelivered. The installer then exited 0 having printed nothing --
    indistinguishable from a healthy install. Round 6 turned a silent degradation
    into a loud abort; round 7's guard turned that loud abort into a SILENT
    SUCCESS.

    Two channels answer it, and neither replaces the other: an installer-wide
    counter drives ``exit 3`` at the end of ``main`` (the exit status is what
    sends an operator or a CI job to look at all), and a durable append gives
    them something to inspect once they do (an in-memory count dies with the
    process).

    HOW THE FAILURE IS DRIVEN HERE, and why it is mostly not the ``chmod 0o500``
    trick used by ``TestAnUnwritableRecordDoesNotKillTheInstaller``: most cases
    pass a 4th-argument ``env_file`` inside a directory that does not exist, so
    the ``touch`` in the first branch fails on the missing parent. ENOENT is not
    overridable by ``CAP_DAC_OVERRIDE``, so those fail identically for root and
    need no ``skipif``.

    THAT IS NOT A UNIVERSAL, AND THIS PARAGRAPH ONCE CLAIMED IT WAS. The earlier
    wording read "no case here can go vacuously green on a CI runner that happens
    to run as uid 0" -- true of every missing-parent case, and FALSE of
    ``test_an_unwritable_ledger_does_not_abort_the_install``, the one case in this
    class that drives failure with ``chmod``. Under uid 0 that case's append
    SUCCEEDS, the ``|| true`` under test never fires, and both its assertions hold
    anyway -- including with the guard deleted. A false universal in the docstring
    a reviewer reads before deciding whether to look is worse than no docstring,
    because it retires the question. The ``chmod`` case now carries the same
    ``skipif`` as the precedent at its sibling class, and
    ``test_a_ledger_in_a_missing_directory_does_not_abort_the_install`` holds the
    same guard by a trigger no uid can walk through, so the guard stays held on a
    rootful runner where the ``skipif`` fires.

    HONEST BOUND, asserted nowhere and stated here so it is not over-read: the
    durable append recovers the PERMISSION case, not the ``ENOSPC`` case. Where
    the trigger is a full disk the append fails too and only the exit status
    survives.
    """

    @staticmethod
    def _run(install_sh_no_main, install_dir, script: str, log_level=None):
        level = f'export LOG_LEVEL="{log_level}"\n' if log_level else ""
        return subprocess.run(
            [
                "bash",
                "-c",
                "set -euo pipefail\n"
                f'export INSTALL_DIR="{install_dir}"\n'
                f"{level}"
                f'source "{install_sh_no_main}"\n'
                f'INSTALL_DIR="{install_dir}"\n' + script,
            ],
            capture_output=True,
            text=True,
        )

    def test_a_failed_record_write_increments_the_counter(
        self, install_sh_no_main, dirs, tmp_path
    ):
        install_dir, _ = dirs
        missing = tmp_path / "absent" / ".env"

        res = self._run(
            install_sh_no_main,
            install_dir,
            f'set_parzival_enablement "false" "failed" "complete" "{missing}"\n'
            'echo "RC=$? COUNT=$PARZIVAL_RECORD_FAILURES" >&2\n',
        )

        assert "RC=0" in res.stderr, (
            "the fail-open contract regressed — set_parzival_enablement must "
            f"still ALWAYS return 0:\n{res.stderr}"
        )
        assert "COUNT=1" in res.stderr, (
            "a write-failure branch was taken and nothing counted it. That is "
            "the whole defect: the failure is named only by a channel that can "
            f"be dead.\n{res.stderr}"
        )

    # THE OTHER THREE COUNTED BRANCHES. The case above drives branch 1 (`touch` on
    # a missing parent) and, until these three landed, it was the ONLY branch with
    # a count assertion anywhere. The pre-existing tests over branches 2-4 assert
    # MESSAGE TEXT, and `parzival_record_failure` re-emits its detail verbatim
    # through `log_error "$detail"` -- so those tests pass whether the site calls
    # the new counting function or the old bare `log_error`. Measured: reverting
    # branch 4 to a bare `log_error` left the whole module green. Branch 4 is the
    # one that fires on a real commit refusal -- read-only remount, EDQUOT,
    # cross-device rename -- i.e. the case where the record is lost while the
    # install completes, which is the entire event this story exists to catch.
    #
    # EACH BRANCH IS DRIVEN BY OVERRIDING THE COMMAND IT TESTS, not by permissions.
    # `mktemp`, `awk` and `mv` are external commands, so a shell function of the
    # same name defined after `source` shadows them -- the idiom `_STUBS` and
    # `_SKIP_NAME_PROMPT` already use in this module. It is deterministic and it is
    # root-proof: a stub returns 1 for uid 0 exactly as it does for uid 1000, so
    # none of these three can go vacuously green the way the `chmod` case can.
    # `env_file` must EXIST for each, or branch 1 fires first and the assertion
    # would pass while testing the wrong branch.

    def test_a_failed_temp_file_is_counted(self, install_sh_no_main, dirs, tmp_path):
        """Branch 2 -- `mktemp` beside the env file fails."""
        install_dir, _ = dirs
        env_file = tmp_path / "present.env"
        env_file.write_text("PARZIVAL_ENABLED=true\n", encoding="utf-8")

        res = self._run(
            install_sh_no_main,
            install_dir,
            "mktemp() { return 1; }\n"
            f'set_parzival_enablement "false" "failed" "complete" "{env_file}"\n'
            'echo "RC=$? COUNT=$PARZIVAL_RECORD_FAILURES" >&2\n',
        )

        assert "RC=0" in res.stderr, (
            "the fail-open contract regressed on the mktemp branch:\n" + res.stderr
        )
        assert "COUNT=1" in res.stderr, (
            "the mktemp branch announced itself only through log_error, which a "
            f"dead stdout drops -- nothing counted it:\n{res.stderr}"
        )
        assert "Could not create a temp file beside" in res.stdout + res.stderr, (
            "a different branch was taken than the one under test, so the count "
            f"above proves nothing about branch 2:\n{res.stdout}{res.stderr}"
        )

    def test_a_failed_record_build_is_counted(self, install_sh_no_main, dirs, tmp_path):
        """Branch 3 -- the `awk` that builds the new record fails."""
        install_dir, _ = dirs
        env_file = tmp_path / "present.env"
        env_file.write_text("PARZIVAL_ENABLED=true\n", encoding="utf-8")

        res = self._run(
            install_sh_no_main,
            install_dir,
            "awk() { return 1; }\n"
            f'set_parzival_enablement "false" "failed" "complete" "{env_file}"\n'
            'echo "RC=$? COUNT=$PARZIVAL_RECORD_FAILURES" >&2\n',
        )

        assert "RC=0" in res.stderr, (
            "the fail-open contract regressed on the awk branch:\n" + res.stderr
        )
        assert "COUNT=1" in res.stderr, (
            "the record-build branch announced itself only through log_error, "
            f"which a dead stdout drops -- nothing counted it:\n{res.stderr}"
        )
        assert "Could not build the Parzival enablement record" in (
            res.stdout + res.stderr
        ), (
            "a different branch was taken than the one under test, so the count "
            f"above proves nothing about branch 3:\n{res.stdout}{res.stderr}"
        )

    def test_a_failed_commit_is_counted(self, install_sh_no_main, dirs, tmp_path):
        """Branch 4 -- the `mv` that commits the record over the env file fails.

        THE MOST OPERATIONALLY SERIOUS OF THE FOUR, and the one measured
        revertible-green. A commit refusal is a read-only remount, an EDQUOT, or
        a cross-device rename: the install completes, the previous record is left
        intact by design, and without a count the run exits 0 saying nothing.
        """
        install_dir, _ = dirs
        env_file = tmp_path / "present.env"
        env_file.write_text("PARZIVAL_ENABLED=true\n", encoding="utf-8")

        res = self._run(
            install_sh_no_main,
            install_dir,
            "mv() { return 1; }\n"
            f'set_parzival_enablement "false" "failed" "complete" "{env_file}"\n'
            'echo "RC=$? COUNT=$PARZIVAL_RECORD_FAILURES" >&2\n',
        )

        assert "RC=0" in res.stderr, (
            "the fail-open contract regressed on the commit branch:\n" + res.stderr
        )
        assert "COUNT=1" in res.stderr, (
            "a real commit refusal -- read-only remount, EDQUOT, cross-device "
            "rename -- went uncounted, so the install exits 0 with the record "
            f"lost:\n{res.stderr}"
        )
        assert "Could not commit the Parzival enablement record" in (
            res.stdout + res.stderr
        ), (
            "a different branch was taken than the one under test, so the count "
            f"above proves nothing about branch 4:\n{res.stdout}{res.stderr}"
        )

    def test_the_counter_survives_a_log_channel_that_cannot_write(
        self, install_sh_no_main, dirs, tmp_path
    ):
        """The load-bearing case — counting AFTER log_error would fail this.

        The increment is placed before both the ``log_error`` and the durable
        append precisely because both are failable. With stdout closed the
        ``log_error`` message is dropped on the floor by its own ``|| true``, and
        an installer whose only record of the failure was that message has no
        record at all. A counter incremented after it inherits the same defect.
        """
        install_dir, _ = dirs
        missing = tmp_path / "absent" / ".env"

        res = self._run(
            install_sh_no_main,
            install_dir,
            "exec 1>&-\n"
            f'set_parzival_enablement "false" "failed" "complete" "{missing}"\n'
            'echo "COUNT=$PARZIVAL_RECORD_FAILURES" >&2\n',
        )

        assert (
            res.returncode == 0
        ), f"a dead stdout ended the run before the count was taken:\n{res.stderr}"
        assert "COUNT=1" in res.stderr, (
            "the failure went uncounted because the LOG could not be written — "
            "the count must be taken whether or not either channel succeeds:\n"
            f"{res.stderr}"
        )

    def test_the_gate_exits_three_when_a_failure_was_recorded(
        self, install_sh_no_main, dirs
    ):
        """3, not 1 — and not 0.

        ``exit 3`` was chosen after censusing this file's exit codes (0, 1 and a
        single 2; no 3). It is deliberately distinct from 1: "the install did its
        work but could not record why Parzival is off" is not the same event as
        "the install failed", and an operator triaging them together learns
        nothing from either.
        """
        install_dir, _ = dirs

        res = self._run(
            install_sh_no_main,
            install_dir,
            "PARZIVAL_RECORD_FAILURES=2\n"
            "parzival_record_status\n"
            'echo "THE GATE DID NOT FIRE" >&2\n',
        )

        assert res.returncode == 3, (
            "a recorded write failure did not reach the operator as a non-zero "
            f"exit status:\n{res.stdout}{res.stderr}"
        )
        assert "THE GATE DID NOT FIRE" not in res.stderr

    def test_the_gate_is_silent_on_a_clean_install(self, install_sh_no_main, dirs):
        """The other half — a gate that always fires is not a gate.

        Without this case the assertion above is satisfied by an unconditional
        ``exit 3``, which would fail every install on the planet.
        """
        install_dir, _ = dirs

        res = self._run(
            install_sh_no_main,
            install_dir,
            "parzival_record_status\n" 'echo "REACHED" >&2\n',
        )

        assert (
            res.returncode == 0
        ), f"the gate fired with no recorded failure:\n{res.stdout}{res.stderr}"
        assert "REACHED" in res.stderr

    def test_a_real_write_failure_reaches_the_gate_in_one_shell(
        self, install_sh_no_main, dirs, tmp_path
    ):
        """The two halves joined -- nothing else in this module joins them.

        Every counter case above stops at the count; every gate case starts from
        a hand-set ``PARZIVAL_RECORD_FAILURES``. Between them sits an untested
        assumption: that the variable a REAL failure increments is the same
        variable the REAL gate reads, in the same shell, with nothing in between
        resetting or shadowing it. Here a genuine write failure is driven and the
        genuine gate then observes it, end to end, in one process.
        """
        install_dir, _ = dirs
        missing = tmp_path / "absent" / ".env"

        res = self._run(
            install_sh_no_main,
            install_dir,
            f'set_parzival_enablement "false" "failed" "complete" "{missing}"\n'
            "parzival_record_status\n"
            'echo "THE GATE DID NOT FIRE" >&2\n',
        )
        combined = res.stdout + res.stderr

        assert res.returncode == 3, (
            "a real write failure did not reach the gate as exit 3 -- the count "
            "and the gate are joined by nothing but an assumption:\n" + combined
        )
        assert "THE GATE DID NOT FIRE" not in res.stderr, combined
        assert "could not record why Parzival is disabled" in combined, combined

    def test_the_durable_record_carries_a_per_entry_timestamp(
        self, install_sh_no_main, dirs, tmp_path
    ):
        """Run identity on every line, and history across runs.

        Without a stamp the ledger reproduces this story's own B-10 one level up:
        run 1 fails, run 2 succeeds, and the operator inspects a file that still
        names a failure. Truncate-on-start would answer that too, and is the
        wrong answer -- it discards the history across repeated failures, which
        is exactly what diagnosing an INTERMITTENT write failure needs. Both
        appends below must survive, each carrying its own stamp.
        """
        install_dir, _ = dirs
        missing = tmp_path / "absent" / ".env"

        res = self._run(
            install_sh_no_main,
            install_dir,
            f'set_parzival_enablement "false" "failed" "complete" "{missing}"\n'
            f'set_parzival_enablement "false" "opt-out" "complete" "{missing}"\n',
        )
        assert res.returncode == 0, res.stderr

        ledger = install_dir / "parzival-record-failures.log"
        assert ledger.exists(), (
            "no durable record was written, so an operator sent here by exit 3 "
            f"finds nothing:\n{res.stdout}{res.stderr}"
        )
        lines = ledger.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2, (
            "the ledger did not APPEND — a truncating writer loses the history "
            f"an intermittent failure is diagnosed from:\n{lines}"
        )
        for line in lines:
            stamp, _, detail = line.partition("\t")
            assert re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", stamp
            ), f"ledger line carries no run identity: {line!r}"
            assert "Parzival enablement record NOT written" in detail, line
        assert "cause=failed" in lines[0] and "cause=opt-out" in lines[1]

    @pytest.mark.skipif(
        hasattr(os, "geteuid") and os.geteuid() == 0,
        reason="chmod(0o500) does not constrain root — as root the ledger append "
        "SUCCEEDS, the `|| true` under test never fires, and both assertions below "
        "hold anyway, including with the guard deleted. Note the direction, because "
        "it is the opposite of the sibling precedent this decorator is copied from: "
        "that one goes falsely RED under root (noisy, safe), this one goes falsely "
        "GREEN (silent, and the worse of the two). The guard stays held under uid 0 "
        "by test_a_ledger_in_a_missing_directory_does_not_abort_the_install, which "
        "no uid can walk through",
    )
    def test_an_unwritable_ledger_does_not_abort_the_install(
        self, install_sh_no_main, tmp_path
    ):
        """🔴 The remedy must not re-create the defect it exists to fix.

        An unguarded ``>>`` that fails under ``set -euo pipefail`` aborts the
        install. That is H1 verbatim, relocated into the remedy for H1 -- and it
        would ship LOOKING like a fix, which is the worst kind, because the
        review that follows sees a guard and stops looking. So the append carries
        ``|| true`` and this case is what holds it there.

        The ledger directory is made unwritable rather than absent, because an
        absent one is the ``mkdir`` case and a read-only one is the permission
        case this whole mechanism is scoped to.
        """
        install_dir = tmp_path / "readonly_install"
        (install_dir / "docker").mkdir(parents=True)
        missing = tmp_path / "absent" / ".env"
        original_mode = install_dir.stat().st_mode
        install_dir.chmod(0o500)  # r-x: the ledger cannot be created here
        try:
            res = self._run(
                install_sh_no_main,
                install_dir,
                f'set_parzival_enablement "false" "failed" "complete" "{missing}"\n'
                'echo "COUNT=$PARZIVAL_RECORD_FAILURES" >&2\n',
            )
        finally:
            install_dir.chmod(original_mode)

        assert res.returncode == 0, (
            "an unwritable LEDGER aborted the install — the append must be "
            "guarded, or the remedy is the defect:\n"
            f"{res.stdout}{res.stderr}"
        )
        assert "COUNT=1" in res.stderr, (
            "the count was lost when the durable append failed; the counter is "
            f"the channel that must survive it:\n{res.stderr}"
        )

    def test_a_ledger_in_a_missing_directory_does_not_abort_the_install(
        self, install_sh_no_main, tmp_path
    ):
        """The same guard, held by a trigger no uid can walk through.

        The permission case above is skipped under uid 0, so on a rootful runner
        it holds nothing at all -- and it is the ``|| true`` on the durable append
        that it holds, the one guard whose removal re-creates this story's
        founding defect INSIDE the remedy for it. ENOENT is not overridable by
        ``CAP_DAC_OVERRIDE``: an append whose parent directory does not exist
        fails to open for root exactly as it does for anyone else. So this case
        runs everywhere the suite runs, and it is what keeps that guard held where
        the case above cannot.

        Deliberately NOT a replacement for the permission case. The mechanism is
        scoped to the permission failure and the ``chmod`` case is the one that
        reproduces it faithfully; this one buys uid-independence, not realism.
        Both, or the guard is held either unfaithfully or not at all.
        """
        install_dir = tmp_path / "no_such_install_dir"  # deliberately never created
        missing = tmp_path / "absent" / ".env"

        res = self._run(
            install_sh_no_main,
            install_dir,
            f'set_parzival_enablement "false" "failed" "complete" "{missing}"\n'
            'echo "COUNT=$PARZIVAL_RECORD_FAILURES" >&2\n',
        )

        assert res.returncode == 0, (
            "a ledger in a missing directory aborted the install — the append "
            "must be guarded, or the remedy is the defect:\n"
            f"{res.stdout}{res.stderr}"
        )
        assert "COUNT=1" in res.stderr, (
            "the count was lost when the durable append failed; the counter is "
            f"the channel that must survive it:\n{res.stderr}"
        )
        # NON-VACUITY CONTROL. If anything ever creates INSTALL_DIR on the way
        # through, the append SUCCEEDS and the two assertions above hold without
        # the guard being exercised at all — this case would then be the very
        # thing it was written to replace.
        assert not install_dir.exists(), (
            "INSTALL_DIR was created during the run, so the ledger append did "
            "not fail and this case proves nothing"
        )

    def test_a_completed_install_is_not_reported_as_interrupted(
        self, install_sh_no_main, dirs
    ):
        """``exit 3`` must not make the EXIT trap tell a second lie.

        ``cleanup`` fires on any non-zero exit once ``INSTALL_STARTED=true`` and
        prints "Installation interrupted" plus "Partial installation exists". Over
        a COMPLETE install that is simply false -- it would replace the silent
        success with a loud untruth, which is not an improvement. ``INSTALL_COMPLETED``
        is set immediately before the gate for exactly this reason.
        """
        install_dir, _ = dirs

        res = self._run(
            install_sh_no_main,
            install_dir,
            "INSTALL_STARTED=true\n"
            "PARZIVAL_RECORD_FAILURES=1\n"
            "INSTALL_COMPLETED=true\n"
            "parzival_record_status\n",
        )
        combined = res.stdout + res.stderr

        assert res.returncode == 3, combined
        assert "Installation interrupted" not in combined, (
            "the EXIT trap called a COMPLETE install interrupted:\n" + combined
        )
        assert "Partial installation exists" not in combined, (
            "the EXIT trap offered `rm -rf` on a COMPLETE installation:\n" + combined
        )
        assert "could not record why Parzival is disabled" in combined, (
            "the gate exited 3 without telling the operator what happened:\n" + combined
        )
        assert "parzival-record-failures.log" in combined, (
            "the gate did not name the file it sent the operator to read — a "
            "file nobody is told to read is not a signal:\n" + combined
        )

    def test_the_interrupted_message_still_fires_on_a_real_abort(
        self, install_sh_no_main, dirs
    ):
        """Non-vacuity control for the case above.

        ``INSTALL_COMPLETED`` narrows the trap's condition, and a narrowing can
        always be overdone. Without this case, deleting the trap body entirely
        would pass. Same script, ``INSTALL_COMPLETED`` left false.
        """
        install_dir, _ = dirs

        res = self._run(
            install_sh_no_main,
            install_dir,
            "INSTALL_STARTED=true\n" "exit 1\n",
        )
        combined = res.stdout + res.stderr

        assert res.returncode == 1
        assert "Installation interrupted" in combined, (
            "the trap no longer reports a genuine abort, so the assertion above "
            f"proves nothing:\n{combined}"
        )


class TestTheGateIsWiredIntoMain:
    """The gate's ENTIRE production reachability, and no test executed it.

    ``main`` ends with exactly two statements — ``INSTALL_COMPLETED=true`` and
    ``parzival_record_status``. They are the only thing connecting the counter to
    the product: without them ``PARZIVAL_RECORD_FAILURES`` is an in-memory
    variable nothing reads, and the exit status that ``DEC-PM445-D5`` calls "what
    sends an operator or a CI job to look" is never produced.

    Nothing held them. The ``install_sh_no_main`` fixture strips ``main "$@"``, so
    ``main`` never runs in any test in this repo; all eight gate cases in the
    class above call ``parzival_record_status`` DIRECTLY and hand-set the flag.
    Measured before this class existed: deleting both lines from ``main`` left the
    module at 40 passed, 0 failed. The gate was deletable from the product with a
    green suite attesting it was there — round 7's silent success restored, one
    level up, wearing a passing test suite.

    WHY TEXT-LEVEL, stated so it is not read as laziness. Executing ``main``
    requires venv creation, pip install, Docker startup and health verification;
    the module docstring records why that is not available here. So this asserts
    the STRUCTURE of the shipped file instead, in the idiom this repo already
    uses — ``tests/integration/test_installation.py`` reads ``install.sh`` and
    asserts substrings over it, and ``install_sh_no_main`` itself asserts that the
    last line is ``main "$@"``.

    WHAT IT DOES AND DOES NOT PROVE, stated because a coverage claim that
    overstates itself is how this story got here three rounds running. It does NOT
    prove the two lines execute, and it is not a substitute for driving ``main``.
    What it does prove is that they are still THERE, still in ``main``, still in
    this order, and still last — which is precisely the mutation that shipped
    green, and it fails on every variant of it: both lines deleted, either line
    deleted alone, or the pair moved above ``show_success_message``.
    """

    @staticmethod
    def _main_body_statements() -> list[str]:
        """Non-blank, non-comment statement lines of ``main``'s body, in order.

        Bounded by ``main() {`` and the next line that is exactly ``}`` at column
        0. Verified at authoring time to be the real terminator: between the two
        there is exactly one such line. Both bounds are asserted rather than
        assumed, so a restructuring of ``install.sh`` fails loudly here instead of
        silently reducing this class to a tautology over an empty list.
        """
        lines = _INSTALL_SH.read_text(encoding="utf-8").splitlines()

        starts = [i for i, ln in enumerate(lines) if ln.startswith("main() {")]
        assert len(starts) == 1, (
            f"expected exactly one `main() {{` at column 0 in install.sh, found "
            f"{len(starts)}. If the installer was restructured, update this class "
            "rather than deleting it — it is the only thing holding the gate's "
            "wiring into the product."
        )
        start = starts[0]

        ends = [i for i in range(start + 1, len(lines)) if lines[i] == "}"]
        assert ends, "could not find the closing `}` of main() in install.sh"
        end = ends[0]

        body = [
            s
            for s in (ln.strip() for ln in lines[start + 1 : end])
            if s and not s.startswith("#")
        ]
        assert body, "main()'s body parsed as empty — this class would prove nothing"
        return body

    def test_the_gate_is_the_last_statement_of_main(self):
        """Delete ``parzival_record_status``, or move it earlier, and this fails.

        Position is load-bearing, not stylistic: the gate exits 3, so anything
        after it in ``main`` would be unreachable on the failure path, and
        anything before it that aborts under ``set -e`` skips the gate entirely.
        """
        body = self._main_body_statements()

        assert body[-1] == "parzival_record_status", (
            "`parzival_record_status` is no longer the last statement of main(). "
            "It is the gate's only call site and the counter's only reader; "
            "without it a recorded write failure exits 0 in silence, which is the "
            f"whole defect this story exists to close. Last statement found: "
            f"{body[-1]!r}"
        )

    def test_the_completion_flag_immediately_precedes_the_gate(self):
        """The other half of the wiring, and it fails independently.

        ``INSTALL_COMPLETED=true`` must be the statement immediately before the
        gate. Dropping it alone is the subtler mutation and the suite was blind to
        it too: the run then exits 3 correctly, but the EXIT trap fires on the
        non-zero status and prints "Installation interrupted" plus an ``rm -rf``
        offer over a COMPLETE installation — the second lie, replacing a silent
        success with a loud untruth. Setting it any earlier is equally wrong: it
        would suppress the trap for genuine aborts in between.
        """
        body = self._main_body_statements()

        assert body[-2:] == ["INSTALL_COMPLETED=true", "parzival_record_status"], (
            "main() no longer ends with `INSTALL_COMPLETED=true` immediately "
            "followed by `parzival_record_status`. Those two lines are the gate's "
            "entire production reachability; every other test in this module "
            "reaches the gate by calling it directly and hand-setting the flag, "
            f"so nothing else would notice. Last two statements found: {body[-2:]!r}"
        )
