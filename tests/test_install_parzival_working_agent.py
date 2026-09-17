"""Install tests for Story 1.2: every install produces a working agent.

FR-1 / AD-45 / AD-68. The installer used to produce a Parzival session agent
only when the operator opted in, so the capability was silently absent because
of a default nobody saw. This module covers the five ACs plus one test per
absorbed debt record.

WHAT "A WORKING AGENT" MEANS -- the phrase all five ACs turn on. It is produced
when the enabled branch of ``setup_parzival`` runs to completion: the deploy
succeeded AND the sole ``true``-write in ``configure_parzival_env`` was reached.
Story 1.1's AC-2 ("no path sets the flag true otherwise") makes the flag a sound
proxy for deployment, but only because that invariant holds -- so every
assertion here checks BOTH the resolved value and the package at AD-70's scope,
via ``_assert_working_agent``. Asserting the flag alone tests Story 1.1's
invariant, not this story's outcome. Asserting the package alone is worse: it is
true on every install including the declined one (``deploy_ai_memory_skills``
creates ``_ai-memory/`` unconditionally), which is why the predicate here is the
conjunction and why ``parzival_package_present`` -- not a restated path -- is
what resolves AD-70's scope.

HARNESS. The pattern is the suite's established one, taken from
``tests/test_install_parzival_enablement_record.py`` (read, not edited, except
where this story's behaviour change falsified its assertions): copy the real
``install.sh`` minus its trailing ``main "$@"`` line -- asserting that line is
present first, so the fixture fails loudly if the installer's structure changes
-- source the copy so the REAL ``setup_parzival``, ``deploy_parzival_v2`` and
``configure_parzival_env`` bodies execute, then override side-effecting
collaborators with bash stubs defined AFTER the source. The copy is regenerated
every run, so it cannot drift from the shipped installer.

TWO DELIBERATE DEPARTURES from the sibling module's drivers:

1. ``env=`` IS PASSED EXPLICITLY, always. The sibling's ``subprocess.run`` calls
   inherit the caller's environment. On a developer machine that environment
   carries live ``QDRANT_API_KEY``, ``LANGFUSE_*``, ``AI_MEMORY_INSTALL_DIR``
   and ``PARZIVAL_*`` values, every one of which reaches the ``install.sh`` copy
   these tests source. ``_bash_env`` builds the environment from scratch instead
   and admits only what the installer needs, so a test can neither read a
   credential nor be steered by an ambient ``PARZIVAL_*`` value.

2. ``deploy_parzival_v2`` IS NOT ALWAYS STUBBED. Both sibling drivers replace it
   unconditionally, which makes AC-4 untestable: the stop points AC-4 governs
   are inside its real body. ``stub_deploy`` selects, and the AC-4 cases run the
   real function with a single command shadowed.

A third departure is per-test rather than structural: the AC-1 closed-stdin case
does NOT hide the greeting-name prompt. The sibling's ``_SKIP_NAME_PROMPT``
forces ``NON_INTERACTIVE=true`` inside ``configure_parzival_env``, which would
hide exactly the abort TD-1065 fixes -- a green test certifying a path that
aborts in production.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
_INSTALL_SH = _SCRIPTS_DIR / "install.sh"

# The AC-5 sweep instrument. /usr/bin/grep, never the shell's: TD-1015 records
# the shell's as a gitignore-aware wrapper that silently under-reports. The -i is
# not optional -- IMPLEMENTATION-SHAPE §5's own episode was a case-sensitive
# matcher missing `Skipping Parzival setup` because it searched for `skipping`,
# while being used to enumerate that very surface.
_AC5_GREP = "/usr/bin/grep"
_AC5_PATTERN = (
    r"Optional\)|declined at install|skipping Parzival setup"
    r"|set INSTALL_PARZIVAL=true to enable|Enable Parzival session agent"
    r"|PARZIVAL_ENABLED=true in docker/\.env|re-run the installer to enable"
)


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


def _bash_env(tmp_path: Path) -> dict[str, str]:
    """The allowlisted environment every bash subprocess here runs under.

    Built from scratch rather than filtered, so a variable that did not exist
    when this was written cannot leak in later. Only PATH, HOME and the locale
    are admitted; HOME is pointed at a scratch directory so nothing the
    installer or its python helpers do can reach the developer's real
    ``~/.ai-memory``.
    """
    home = tmp_path / "fake_home"
    home.mkdir(exist_ok=True)
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }


# Side-effecting collaborators of setup_parzival. Defined AFTER the source so
# they override the real definitions; setup_parzival itself is always real.
# deploy_parzival_v2 is NOT here -- it is selected per test, because AC-4's stop
# points live inside its real body.
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


def _run(
    install_sh_copy: Path,
    install_dir: Path,
    project_dir: Path,
    tmp_path: Path,
    *,
    source_package_present: bool = True,
    deployed_before: bool = False,
    non_interactive: str = "true",
    install_parzival: str | None = None,
    stub_deploy: bool = True,
    deploy_fails: bool = False,
    deploy_creates_package: bool = True,
    with_notice: bool = False,
    stdin: str = "",
    extra_bash: str = "",
    post_bash: str = "",
) -> subprocess.CompletedProcess:
    """Drive the real ``setup_parzival``, optionally wrapped as ``main`` wraps it.

    ``with_notice`` reproduces ``main``'s sequence exactly -- sample, call,
    sample, ``announce_parzival_state_change`` -- which is the only way to
    observe the AD-66 notice and Task 4's report the way an operator would.

    Two different directories are both called ``_ai-memory`` and must not be
    conflated: ``source_package_present`` seeds ``$INSTALL_DIR/_ai-memory``, the
    shipped package ``setup_parzival``'s first guard checks for, while
    ``deployed_before`` seeds ``$PROJECT_PATH/_ai-memory/pov``, the deployment
    at AD-70's scope that the probe samples. The bare project-side parent cannot
    discriminate -- ``deploy_ai_memory_skills`` creates it on every install.
    """
    if source_package_present:
        (install_dir / "_ai-memory").mkdir(parents=True, exist_ok=True)
    if deployed_before:
        (project_dir / "_ai-memory" / "pov").mkdir(parents=True, exist_ok=True)

    install_parzival_line = (
        f'INSTALL_PARZIVAL="{install_parzival}"' if install_parzival is not None else ""
    )
    if stub_deploy:
        side_effect = (
            f'mkdir -p "{project_dir}/_ai-memory/pov";'
            if (deploy_creates_package and not deploy_fails)
            else ""
        )
        deploy_line = f"deploy_parzival_v2() {{ {side_effect} return {1 if deploy_fails else 0}; }}"
    else:
        deploy_line = ""

    if with_notice:
        call = """
_before_value=$(parzival_read_enabled_value "$INSTALL_DIR/docker/.env")
_before_package=$(parzival_package_present "$PROJECT_PATH")
setup_parzival
_after_value=$(parzival_read_enabled_value "$INSTALL_DIR/docker/.env")
_after_package=$(parzival_package_present "$PROJECT_PATH")
announce_parzival_state_change "$_before_value" "$_before_package" "$_after_value" "$_after_package"
"""
    else:
        call = "setup_parzival\n"

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
{deploy_line}
{extra_bash}
{call}
{post_bash}
"""
    return subprocess.run(
        ["bash", "-c", bash_cmd],
        capture_output=True,
        text=True,
        input=stdin,
        env=_bash_env(tmp_path),
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


def _assert_record(env: dict[str, str], value: str, cause: str, condition: str) -> None:
    """Assert all three keys together -- the record declares one shape, not three."""
    assert env.get("PARZIVAL_ENABLED") == value, f"value: {env!r}"
    assert env.get("PARZIVAL_ENABLED_CAUSE") == cause, f"cause: {env!r}"
    assert env.get("PARZIVAL_ENABLED_CONDITION") == condition, f"condition: {env!r}"


def _assert_working_agent(install_dir: Path, project_dir: Path, where: str) -> None:
    """The conjunction the ACs actually require: resolved value AND package.

    The package half is asserted through ``parzival_package_present``'s own
    predicate rather than a restated literal path (AD-70 was corrected twice
    because five sites restated it; TD-1097). The value half is asserted through
    the record because ``parzival_read_enabled_value`` reads exactly this key.
    """
    env = _env_values(install_dir)
    assert env.get("PARZIVAL_ENABLED") == "true", f"{where}: value not enabled: {env!r}"
    assert (
        env.get("PARZIVAL_ENABLED_CAUSE") == ""
    ), f"{where}: cause not cleared: {env!r}"
    assert (
        project_dir / "_ai-memory" / "pov"
    ).is_dir(), f"{where}: package absent at AD-70's scope"


# ---------------------------------------------------------------------------
# AC-1 -- a fresh INTERACTIVE install produces a working agent, and nothing it
# is fed on stdin changes that.
# ---------------------------------------------------------------------------


class TestInteractiveInstallAlwaysProducesAWorkingAgent:
    """AC-1. Three stdin cases, each RED against unchanged code.

    ``n`` is the case that matters. At baseline it failed the ``^(y|yes)$``
    match and reached the decline write-site, so it asserts the decline's
    REMOVAL directly, where the other two assert only that nothing blocked. It
    also feeds input the non-interactive arm never consumes, which is what keeps
    AC-1 and AC-2 from proving one axis twice once both end on one enable path.
    """

    def test_an_explicit_n_still_produces_a_working_agent(
        self, install_sh_no_main, dirs, tmp_path
    ):
        install_dir, project_dir = dirs
        res = _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            non_interactive="false",
            stdin="n\n",
        )
        assert res.returncode == 0, res.stdout + res.stderr
        _assert_working_agent(install_dir, project_dir, "interactive n")

    def test_bare_enter_produces_a_working_agent(
        self, install_sh_no_main, dirs, tmp_path
    ):
        install_dir, project_dir = dirs
        res = _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            non_interactive="false",
            stdin="\n",
        )
        assert res.returncode == 0, res.stdout + res.stderr
        _assert_working_agent(install_dir, project_dir, "interactive bare enter")

    def test_closed_stdin_produces_a_working_agent(
        self, install_sh_no_main, dirs, tmp_path
    ):
        """The greeting-name prompt is deliberately NOT hidden here (TD-1065).

        Story 1.1's ``_SKIP_NAME_PROMPT`` forces ``NON_INTERACTIVE=true`` inside
        ``configure_parzival_env``. Using it here would hide the very abort
        TD-1065 fixes: with the enablement question removed, an exhausted stdin
        reaches the unguarded name ``read``, which returns non-zero under the
        global errexit and kills the installer AFTER the record says enabled.
        The run completing is therefore part of the assertion, not scaffolding
        around it.
        """
        install_dir, project_dir = dirs
        res = _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            non_interactive="false",
            stdin="",
        )
        assert res.returncode == 0, (
            "an exhausted stdin must not abort the run -- TD-1065:\n"
            + res.stdout
            + res.stderr
        )
        _assert_working_agent(install_dir, project_dir, "interactive closed stdin")
        assert (
            _env_values(install_dir).get("PARZIVAL_USER_NAME") == "Developer"
        ), "on EOF the default greeting name must stand"

    def test_the_installer_solicits_nothing_on_enablement(self, install_sh_no_main):
        """Option A's actual requirement: not "the default flipped" but "nothing
        is asked". A default flip would leave the read in place and still satisfy
        the three cases above, because all three would answer it the same way.

        The predicate is a PROMPTED read, ``read ... -p``, not the word ``read``.
        Soliciting is what ``-p`` does; ``setup_parzival`` also reads from a
        here-string to walk the retained-backup list, and a blanket ban on the
        token would fail that for no reason -- it asks the operator nothing.
        """
        body = subprocess.run(
            ["bash", "-c", f'source "{install_sh_no_main}"; declare -f setup_parzival'],
            capture_output=True,
            text=True,
        )
        assert body.returncode == 0, body.stdout + body.stderr
        assert "Enable Parzival session agent" not in body.stdout, body.stdout
        prompted = [
            line
            for line in body.stdout.splitlines()
            if re.search(r"\bread\b[^\n]*\s-\w*p\b", line)
        ]
        assert (
            not prompted
        ), "setup_parzival must solicit no input on enablement:\n" + "\n".join(prompted)


class TestStdinNoLongerConsumedByTheRemovedPrompt:
    """A known behaviour change of option A, pinned so it is visible.

    With the enablement question gone, whatever a scripted install piped to
    answer it now falls through to the greeting-name prompt. A script sending
    ``n\\n`` sets the operator's display name to ``n``. This is a consequence of
    removing the prompt, not of TD-1065, and re-adding a consumer for the
    removed prompt would be re-adding the prompt. It is asserted rather than
    merely noted so that it cannot change silently.
    """

    def test_input_meant_for_the_removed_prompt_lands_on_the_name_prompt(
        self, install_sh_no_main, dirs, tmp_path
    ):
        install_dir, project_dir = dirs
        res = _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            non_interactive="false",
            stdin="n\n",
        )
        assert res.returncode == 0, res.stdout + res.stderr
        assert _env_values(install_dir).get("PARZIVAL_USER_NAME") == "n"


# ---------------------------------------------------------------------------
# AC-2 -- a fresh NON-INTERACTIVE install produces a working agent.
# ---------------------------------------------------------------------------


class TestNonInteractiveInstallProducesAWorkingAgent:
    """AC-2, plus the parity case and the one real negative on the variable."""

    def test_unset_install_parzival_produces_a_working_agent(
        self, install_sh_no_main, dirs, tmp_path
    ):
        install_dir, project_dir = dirs
        res = _run(install_sh_no_main, install_dir, project_dir, tmp_path)
        assert res.returncode == 0, res.stdout + res.stderr
        _assert_working_agent(install_dir, project_dir, "non-interactive unset")

    def test_install_parzival_false_also_produces_a_working_agent(
        self, install_sh_no_main, dirs, tmp_path
    ):
        """The parity case. ``INSTALL_PARZIVAL`` is opt-IN: INSTALL.md ships the
        contract that only the literal string ``true`` enables and every other
        value behaves as unset, so ``false`` was never a decline. DEC-PM441-D1
        rules that it converts, and there is no supported disable path for it to
        remove.
        """
        install_dir, project_dir = dirs
        res = _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            install_parzival="false",
        )
        assert res.returncode == 0, res.stdout + res.stderr
        _assert_working_agent(install_dir, project_dir, "INSTALL_PARZIVAL=false")

    def test_install_parzival_true_still_takes_the_explicit_opt_in_path(
        self, install_sh_no_main, dirs, tmp_path
    ):
        """The one real negative on this variable: the opt-in path is unchanged,
        and still says so. Without this, "everything enables" could be satisfied
        by deleting the branch entirely.
        """
        install_dir, project_dir = dirs
        res = _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            install_parzival="true",
        )
        assert res.returncode == 0, res.stdout + res.stderr
        _assert_working_agent(install_dir, project_dir, "INSTALL_PARZIVAL=true")
        assert "INSTALL_PARZIVAL=true" in (res.stdout + res.stderr)


class TestBothEntryMechanismsChanged:
    """AD-45: the two axes are orthogonal and changing one is not a discharge.

    The behavioural tests above converge on one enable path after the change, so
    neither of them can tell "both arms were changed" from "one arm was changed
    and the other now falls through to it". This reads the arms themselves.
    """

    def test_neither_arm_writes_opt_out(self, install_sh_no_main):
        body = subprocess.run(
            ["bash", "-c", f'source "{install_sh_no_main}"; declare -f setup_parzival'],
            capture_output=True,
            text=True,
        )
        assert body.returncode == 0, body.stdout + body.stderr
        assert "opt-out" not in body.stdout, (
            "FR-1 leaves opt-out with zero writers:\n" + body.stdout
        )

    def test_opt_out_has_zero_writers_anywhere_in_the_installer(self):
        """Derived from the shipped file, not from a count quoted in a document.

        The write-site set is re-derived here rather than pinned: the story's own
        table went stale by a whole row, and the count changes with this story.
        """
        writes = [
            line
            for line in _INSTALL_SH.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("set_parzival_enablement ")
        ]
        assert writes, "the matcher found no write-sites at all -- it has rotted"
        assert not [w for w in writes if "opt-out" in w], writes


# ---------------------------------------------------------------------------
# AC-3 -- existing installs convert: opt-out and unknown. failed re-attempts.
# ---------------------------------------------------------------------------


def _seed_record(install_dir: Path, text: str) -> None:
    (install_dir / "docker" / ".env").write_text(text, encoding="utf-8")


class TestExistingInstallsConvert:
    """AC-3 / AD-68. The conversion domain is opt-out + unknown.

    ``unknown`` is the MAJORITY case -- every install predating Story 1.1 has no
    cause key at all -- so its three shapes (empty, absent, unrecognised token)
    are covered as first-class cases, not as edge cases.
    """

    def test_an_opt_out_install_converts(self, install_sh_no_main, dirs, tmp_path):
        install_dir, project_dir = dirs
        _seed_record(
            install_dir,
            "PARZIVAL_ENABLED=false\n"
            "PARZIVAL_ENABLED_CAUSE=opt-out\n"
            "PARZIVAL_ENABLED_CONDITION=complete\n",
        )
        res = _run(install_sh_no_main, install_dir, project_dir, tmp_path)
        assert res.returncode == 0, res.stdout + res.stderr
        _assert_working_agent(install_dir, project_dir, "opt-out conversion")

    def test_an_empty_cause_converts(self, install_sh_no_main, dirs, tmp_path):
        install_dir, project_dir = dirs
        _seed_record(
            install_dir,
            "PARZIVAL_ENABLED=false\n"
            "PARZIVAL_ENABLED_CAUSE=\n"
            "PARZIVAL_ENABLED_CONDITION=complete\n",
        )
        res = _run(install_sh_no_main, install_dir, project_dir, tmp_path)
        assert res.returncode == 0, res.stdout + res.stderr
        _assert_working_agent(install_dir, project_dir, "empty-cause conversion")

    def test_an_absent_cause_key_converts(self, install_sh_no_main, dirs, tmp_path):
        """The majority case: every install predating Story 1.1 is in it. The
        record carries the VALUE key only -- no cause key, no condition key.
        """
        install_dir, project_dir = dirs
        _seed_record(install_dir, "PARZIVAL_ENABLED=false\n")
        res = _run(install_sh_no_main, install_dir, project_dir, tmp_path)
        assert res.returncode == 0, res.stdout + res.stderr
        _assert_working_agent(install_dir, project_dir, "absent-cause conversion")
        assert (
            _env_values(install_dir).get("PARZIVAL_ENABLED_CONDITION") == "complete"
        ), "the back-fill must add the condition key an old record never carried"

    def test_an_unrecognised_cause_token_converts(
        self, install_sh_no_main, dirs, tmp_path
    ):
        """A typo'd cause resolves to unknown, and unknown converts. Asserted with
        a token that is NOT a prefix of a real cause, so a matcher that
        accidentally accepted `fail*` would not pass this.
        """
        install_dir, project_dir = dirs
        _seed_record(
            install_dir,
            "PARZIVAL_ENABLED=false\n"
            "PARZIVAL_ENABLED_CAUSE=faled\n"
            "PARZIVAL_ENABLED_CONDITION=complete\n",
        )
        res = _run(install_sh_no_main, install_dir, project_dir, tmp_path)
        assert res.returncode == 0, res.stdout + res.stderr
        _assert_working_agent(install_dir, project_dir, "unrecognised-token conversion")


class TestFailedReattemptsDeploymentRatherThanConverting:
    """AC-3's surviving assertion, as TWO cases.

    Under the adopted reading ``failed``, ``opt-out`` and ``unknown`` all reach
    ``deploy_parzival_v2``, so a successful ``failed`` retry ends ENABLED and may
    legitimately emit a notice. "The flag is not forced true" is therefore
    observable only when the retry itself fails -- which is why asserting "no
    converted token" or "the flag stays false" on a SUCCESSFUL retry would fail a
    conforming implementation and pass only the cause branch Task 3 forbids.
    """

    def test_a_failed_install_whose_retry_fails_stays_failed(
        self, install_sh_no_main, dirs, tmp_path
    ):
        install_dir, project_dir = dirs
        _seed_record(
            install_dir,
            "PARZIVAL_ENABLED=false\n"
            "PARZIVAL_ENABLED_CAUSE=failed\n"
            "PARZIVAL_ENABLED_CONDITION=complete\n",
        )
        res = _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            deploy_fails=True,
            extra_bash="_deploy_called=0\n",
        )
        assert res.returncode == 0, res.stdout + res.stderr
        _assert_record(_env_values(install_dir), "false", "failed", "complete")

    def test_the_deploy_is_re_attempted_on_a_failed_record(
        self, install_sh_no_main, dirs, tmp_path
    ):
        """ "Does not convert" must not be built as "skip the site entirely". The
        marker proves the deploy was invoked, not merely that the record moved.
        """
        install_dir, project_dir = dirs
        _seed_record(
            install_dir,
            "PARZIVAL_ENABLED=false\n"
            "PARZIVAL_ENABLED_CAUSE=failed\n"
            "PARZIVAL_ENABLED_CONDITION=complete\n",
        )
        res = _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            stub_deploy=False,
            extra_bash=(
                'deploy_parzival_v2() { echo "deploy_invoked=1"; '
                f'mkdir -p "{project_dir}/_ai-memory/pov"; return 1; }}\n'
            ),
        )
        assert res.returncode == 0, res.stdout + res.stderr
        assert "deploy_invoked=1" in (res.stdout + res.stderr)

    def test_a_failed_install_whose_retry_succeeds_ends_enabled(
        self, install_sh_no_main, dirs, tmp_path
    ):
        install_dir, project_dir = dirs
        _seed_record(
            install_dir,
            "PARZIVAL_ENABLED=false\n"
            "PARZIVAL_ENABLED_CAUSE=failed\n"
            "PARZIVAL_ENABLED_CONDITION=complete\n",
        )
        res = _run(install_sh_no_main, install_dir, project_dir, tmp_path)
        assert res.returncode == 0, res.stdout + res.stderr
        _assert_working_agent(install_dir, project_dir, "failed retry success")


class TestTheGateIsAnEffectiveStateDiffNotADeploySkip:
    """AC-3's gate-ordering negative, in falsifiable form.

    An already-enabled install must stay enabled, must emit NO notice, and must
    STILL be redeployed. The third assertion is the load-bearing one: redeploying
    on every enabled run IS the update path (``_ai-memory/`` is overwritten
    wholesale on every enabled install), so a gate that returns early on
    "effective state enabled" silently stops every enabled project from receiving
    package updates. All three are RED at baseline -- the non-interactive arm
    wrote false/opt-out and returned, so the value went false, the notice read
    ``parzival_notice=disabled`` and no deploy ran.
    """

    def test_an_already_enabled_install_stays_enabled_silently_and_is_redeployed(
        self, install_sh_no_main, dirs, tmp_path
    ):
        install_dir, project_dir = dirs
        _seed_record(
            install_dir,
            "PARZIVAL_ENABLED=true\n"
            "PARZIVAL_ENABLED_CAUSE=\n"
            "PARZIVAL_ENABLED_CONDITION=complete\n",
        )
        res = _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            deployed_before=True,
            with_notice=True,
            stub_deploy=False,
            extra_bash=(
                'deploy_parzival_v2() { echo "deploy_invoked=1"; '
                f'mkdir -p "{project_dir}/_ai-memory/pov"; return 0; }}\n'
            ),
        )
        combined = res.stdout + res.stderr
        assert res.returncode == 0, combined
        # (a) still enabled
        _assert_working_agent(install_dir, project_dir, "enabled re-run")
        # (b) an unchanged effective state is not reported as a conversion
        assert "parzival_notice=" not in combined, combined
        # (c) and the package was still redeployed -- this is the update path
        assert "deploy_invoked=1" in combined, combined


class TestTheBeforeSampleStaysAheadOfSetupParzival:
    """Verify-only: main's before-sample precedes all of setup_parzival's
    branching, and no copy of it was moved inside the function.

    A mis-placed sample does not change what is deployed; it changes whether the
    notice is correct. Read positionally from main's own source, because a driver
    that writes the sequence itself would stay green even if main's wiring were
    deleted.
    """

    def _main_body(self) -> str:
        text = _INSTALL_SH.read_text(encoding="utf-8")
        start = text.index("\nmain() {\n") + 1
        end = text.index("\ncheck_existing_installation() {", start)
        return text[start:end]

    def test_the_sample_precedes_the_call_in_main(self):
        body = self._main_body()
        before = body.index('parzival_read_enabled_value "$INSTALL_DIR/docker/.env")')
        call = body.index("\n    setup_parzival\n")
        assert before < call, body

    def test_setup_parzival_contains_no_copy_of_the_sample(self, install_sh_no_main):
        body = subprocess.run(
            ["bash", "-c", f'source "{install_sh_no_main}"; declare -f setup_parzival'],
            capture_output=True,
            text=True,
        )
        assert body.returncode == 0, body.stdout + body.stderr
        assert "parzival_read_enabled_value" not in body.stdout, body.stdout
        assert "announce_parzival_state_change" not in body.stdout, body.stdout


# ---------------------------------------------------------------------------
# AC-5 -- no installer string describes the agent as optional.
# ---------------------------------------------------------------------------


class TestNoInstallerStringCallsTheAgentOptional:
    """AC-5, with a stated matcher and a stated exclusion set.

    A count without a stated exclusion set is unsupportable, and so is an
    exclusion set without a case-insensitive matcher. Every hit the matcher
    returns is classified below; an unclassified hit fails the test rather than
    being dropped.
    """

    def _hits(self) -> list[str]:
        res = subprocess.run(
            [_AC5_GREP, "-niE", _AC5_PATTERN, str(_INSTALL_SH)],
            capture_output=True,
            text=True,
        )
        # grep exits 1 on no match, which is a legitimate outcome here.
        assert res.returncode in (0, 1), res.stderr
        # `grep -n` over a SINGLE file prints `lineno:content`, one colon prefix.
        # Stripping two fields silently emptied every hit, so the "unclassified"
        # list came back full of blanks and the check reported a defect it had
        # not actually found -- and would equally have reported clean if every
        # hit had been blanked to a value the table happens to accept.
        return [line.partition(":")[2] for line in res.stdout.splitlines()]

    # Hits that are not about the Parzival agent at all. Identified by quoted
    # string, never by line number -- positions move, these strings do not.
    _EXCLUDED_NOT_PARZIVAL = (
        "Jira Cloud Integration (Optional)",
        "GitHub Integration (Optional)",
        "Langfuse LLM Observability (Optional)",
        "Multi-Provider Dispatch (Optional)",
        "# Langfuse LLM Observability (optional)",
        "# monitoring/ — monitoring module (optional)",
        "# .claude/skills/ — Claude Code skills (optional)",
        "# .claude/agents/ — Claude Code agents (optional)",
        "# templates/ — best practices seeding templates (optional)",
        "# docs/ — documentation (optional)",
        "# Seed best practices collection (AC 7.5.4 - optional)",
        "Monitoring API did not start (this is optional)",
    )
    # Parzival, but a failure message rather than optionality framing.
    _EXCLUDED_NOT_OPTIONALITY = (
        "Parzival V2 package not found in source repo — skipping Parzival setup",
    )
    # Matched, but a claim-half defect routed elsewhere, not an AC-5 rewording.
    # AD-67 declares it forbidden -- every non-interactive install reached that
    # arm and none of them declined -- but AC-5 quantifies over optionality
    # framing, not over claims, so absorbing it here would be scope creep
    # dressed as a fix. It is reported for routing and deliberately left in
    # place; this entry is what stops it being dropped instead.
    _ROUTED_CLAIM_HALF = ("declined at install",)

    # In scope, and reworded rather than removed. The remedy half of the summary
    # panel's opt-out arm survives as a re-run instruction; what goes is the
    # clause naming the flag as the operator's lever, which FR-1/AD-68 makes
    # false rather than merely optional-sounding.
    _REWORDED_IN_SCOPE = ("Re-run the installer to enable it",)

    # Removed outright by this story. The absence assertion is stronger than the
    # rewording it replaces.
    _MUST_BE_ABSENT = (
        "Parzival Session Agent (Optional)",
        "Enable Parzival session agent",
        "No response on stdin (EOF)",
        "Skipping Parzival setup (PARZIVAL_ENABLED=false)",
        "set INSTALL_PARZIVAL=true to enable",
    )

    def test_every_removed_string_is_gone(self):
        text = _INSTALL_SH.read_text(encoding="utf-8")
        for s in self._MUST_BE_ABSENT:
            assert s not in text, f"still present: {s!r}"

    def test_every_surviving_hit_is_classified(self):
        """The comparison is case-INSENSITIVE, and that is not a nicety.

        The matcher runs under ``-i``; a case-sensitive classifier beside it
        reproduces exactly the defect IMPLEMENTATION-SHAPE §5 records -- and did,
        while this test was being written: the shipped line reads "Re-run the
        installer to enable it" and the table carried the lower-case form, so a
        correctly-reworded string was reported as unclassified.
        """
        classified = tuple(
            e.lower()
            for e in (
                self._EXCLUDED_NOT_PARZIVAL
                + self._EXCLUDED_NOT_OPTIONALITY
                + self._ROUTED_CLAIM_HALF
                + self._REWORDED_IN_SCOPE
            )
        )
        unclassified = []
        for hit in self._hits():
            h = hit.strip()
            if not any(e in h.lower() for e in classified):
                unclassified.append(h)
        assert not unclassified, (
            "the AC-5 sweep returned hits this exclusion table does not classify. "
            "Classify them; never drop them:\n" + "\n".join(unclassified)
        )

    def test_the_matcher_itself_still_matches_something(self):
        """Positive control. An AC-5 sweep whose matcher has rotted returns zero
        hits and reports the surface as clean -- the same shape as a test that
        cannot fail.
        """
        assert self._hits(), "the AC-5 matcher returned nothing at all -- it has rotted"

    def test_the_summary_panel_remedy_no_longer_tells_the_operator_to_set_the_flag(
        self,
    ):
        """Under FR-1/AD-68 that remedy is FALSE, not merely optional-sounding:
        the conversion makes the flag no longer the operator's lever. Rewriting
        it is in scope; deciding whether the arm survives at all is not.
        """
        text = _INSTALL_SH.read_text(encoding="utf-8")
        assert "Set PARZIVAL_ENABLED=true in docker/.env" not in text, text[:0] or (
            "the opt-out arm's remedy still names a lever this story removes"
        )


# ---------------------------------------------------------------------------
# AC-4 -- a conversion that stops partway is stated, recoverable and reported.
#
# The failure is injected INSIDE the real deploy_parzival_v2 body, because that
# is where the stop points are. Both sibling drivers stub the function out, which
# is why AC-4 had no coverage: a stubbed deploy cannot stop partway. `cp` is
# shadowed so exactly one call fails and every other runs `command cp`;
# set_parzival_enablement uses no `cp` at all, so the record write still works
# and the record can therefore carry the condition.
#
# The record commit's `mv` is deliberately NOT the injection point. On this path
# `mv() { return 1; }` reaches exactly one `mv` -- set_parzival_enablement's
# commit rename -- so it fails the record write itself, the record cannot carry
# condition=partial, and what it produces is the exit-3 path instead.
# ---------------------------------------------------------------------------

# Fail only the package copy: its source arguments are the globbed entries of
# $INSTALL_DIR/_ai-memory. By the time it runs, rm -rf "$dst" has already gone,
# so this is unambiguously an after-touch stop.
_FAIL_PACKAGE_COPY = """
cp() {
    local a
    for a in "$@"; do
        case "$a" in
            "$INSTALL_DIR"/_ai-memory/*) return 1 ;;
        esac
    done
    command cp "$@"
}
"""

# Fail only the _memory backup: a before-touch stop, and TD-537's site.
_FAIL_MEMORY_BACKUP = """
cp() {
    local a
    for a in "$@"; do
        case "$a" in
            "$PROJECT_PATH"/_ai-memory/_memory) return 1 ;;
        esac
    done
    command cp "$@"
}
"""

# Fail only the sanctum backup, which runs AFTER the _memory backup has
# completed -- so a stop here leaves a COMPLETE _memory backup on disk.
_FAIL_SANCTUM_BACKUP = """
cp() {
    local a
    for a in "$@"; do
        case "$a" in
            "$PROJECT_PATH"/_ai-memory/sanctum) return 1 ;;
        esac
    done
    command cp "$@"
}
"""

# Fail only a WRITE INTO the restored sanctum tree. Deliberately distinct from
# the backup shadow above: that one matches the source directory exactly, with
# no trailing slash, while this matches paths BENEATH the destination. By the
# time the sanctum restore loop runs, the _memory backup has already been
# removed -- which is the state the "names no missing path" case needs.
_FAIL_SANCTUM_RESTORE = """
cp() {
    local a
    for a in "$@"; do
        case "$a" in
            "$PROJECT_PATH"/_ai-memory/sanctum/*) return 1 ;;
        esac
    done
    command cp "$@"
}
"""


def _seed_existing_install(install_dir: Path, project_dir: Path) -> None:
    """A shipped source package plus a deployed project carrying operator data."""
    src = install_dir / "_ai-memory" / "pov"
    src.mkdir(parents=True, exist_ok=True)
    (src / "shipped.md").write_text("shipped\n", encoding="utf-8")

    dst = project_dir / "_ai-memory"
    (dst / "pov").mkdir(parents=True, exist_ok=True)
    (dst / "_memory").mkdir(parents=True, exist_ok=True)
    (dst / "_memory" / "user-note.md").write_text(
        "operator content\n", encoding="utf-8"
    )
    (dst / "sanctum" / "parzival").mkdir(parents=True, exist_ok=True)
    (dst / "sanctum" / "parzival" / "identity.md").write_text(
        "instance identity\n", encoding="utf-8"
    )


def _backup_dirs(install_dir: Path) -> list[Path]:
    """Every backup directory deploy_parzival_v2 could have created this run."""
    return sorted(install_dir.glob(".parzival-*backup*"))


class TestAStopAfterTheDestinationIsTouched:
    """AC-4. Stated, recoverable, AND reported -- recording without reporting
    does not satisfy it.

    RED at baseline on every assertion: errexit is off inside
    deploy_parzival_v2, so the failing copy was ignored, the function ran on to
    log_success and returned 0, and configure_parzival_env then recorded
    true / "" / complete over a package that is not there.
    """

    def test_the_condition_is_stated_in_the_record(
        self, install_sh_no_main, dirs, tmp_path
    ):
        install_dir, project_dir = dirs
        _seed_existing_install(install_dir, project_dir)
        res = _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            install_parzival="true",
            stub_deploy=False,
            extra_bash=_FAIL_PACKAGE_COPY,
        )
        assert res.returncode == 0, res.stdout + res.stderr
        _assert_record(_env_values(install_dir), "false", "failed", "partial")

    def test_the_condition_is_reported_with_a_machine_token(
        self, install_sh_no_main, dirs, tmp_path
    ):
        """A literal token, never a prose log string, and deliberately not a
        member of the parzival_notice= family -- that notice is the cause-blind
        state-change diff, it has no condition input, and it stays SILENT when a
        stop leaves the effective state unchanged, which is the usual case here.
        """
        install_dir, project_dir = dirs
        _seed_existing_install(install_dir, project_dir)
        res = _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            install_parzival="true",
            stub_deploy=False,
            with_notice=True,
            extra_bash=_FAIL_PACKAGE_COPY,
        )
        combined = res.stdout + res.stderr
        assert res.returncode == 0, combined
        assert "parzival_condition=partial" in combined, combined

    def test_the_report_names_the_retained_backups(
        self, install_sh_no_main, dirs, tmp_path
    ):
        install_dir, project_dir = dirs
        _seed_existing_install(install_dir, project_dir)
        res = _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            install_parzival="true",
            stub_deploy=False,
            extra_bash=_FAIL_PACKAGE_COPY,
        )
        combined = res.stdout + res.stderr
        assert res.returncode == 0, combined
        retained = _backup_dirs(install_dir)
        assert retained, "an after-touch stop must KEEP the backups"
        for path in retained:
            assert str(path) in combined, f"{path} not named in the report:\n{combined}"

    def test_the_report_names_no_path_that_does_not_exist(
        self, install_sh_no_main, dirs, tmp_path
    ):
        """Every named path must be there at the moment of the stop.

        The stop is forced INSIDE THE SANCTUM RESTORE LOOP, and that placement is
        the whole test. By then ``rm -rf "$mem_backup"`` has already run, so the
        _memory backup is gone while its variable is still in scope: a report
        built from the variables rather than from what exists would hand the
        operator a directory that is not there. Forcing the stop at the package
        copy instead would leave BOTH backups present and the assertion would
        hold vacuously -- which is what an earlier version of this test did, and
        it was the one test in this module that could not fail at baseline.
        """
        install_dir, project_dir = dirs
        _seed_existing_install(install_dir, project_dir)
        res = _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            install_parzival="true",
            stub_deploy=False,
            extra_bash=_FAIL_SANCTUM_RESTORE,
        )
        combined = res.stdout + res.stderr
        assert res.returncode == 0, combined
        named = [
            token
            for line in combined.splitlines()
            for token in line.split()
            if ".parzival-" in token and "backup" in token
        ]
        assert named, "an after-touch stop must name the backups it retained"
        for token in named:
            assert Path(token).is_dir(), f"named a missing path: {token!r}"
        assert not any(
            "memory-backup" in token for token in named
        ), f"the _memory backup was already removed by this point: {named}"

    def test_the_backups_still_hold_the_operator_content(
        self, install_sh_no_main, dirs, tmp_path
    ):
        """Recoverable means the content survived, not merely that a directory
        with the right name is present.
        """
        install_dir, project_dir = dirs
        _seed_existing_install(install_dir, project_dir)
        _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            install_parzival="true",
            stub_deploy=False,
            extra_bash=_FAIL_PACKAGE_COPY,
        )
        found = {
            p.name: p.read_text(encoding="utf-8")
            for backup in _backup_dirs(install_dir)
            for p in backup.rglob("*")
            if p.is_file()
        }
        assert found.get("user-note.md") == "operator content\n", found
        assert found.get("identity.md") == "instance identity\n", found

    def test_the_report_warns_against_the_installers_own_cleanup_advice(
        self, install_sh_no_main, dirs, tmp_path
    ):
        """The retained backups live under INSTALL_DIR, and an aborted full-mode
        run prints "To clean up and retry: rm -rf $INSTALL_DIR". Unqualified,
        the installer's own advice tells the operator to delete the only
        recovery copy it just handed them.
        """
        install_dir, project_dir = dirs
        _seed_existing_install(install_dir, project_dir)
        res = _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            install_parzival="true",
            stub_deploy=False,
            extra_bash=_FAIL_PACKAGE_COPY,
        )
        combined = res.stdout + res.stderr
        assert "Copy them elsewhere before running" in combined, combined

    def test_configure_parzival_env_does_not_run_after_the_stop(
        self, install_sh_no_main, dirs, tmp_path
    ):
        """Its two-argument true-write would record enabled and reset the
        condition to complete over a package that is not there -- undoing both
        halves of AC-4 in one call.
        """
        install_dir, project_dir = dirs
        _seed_existing_install(install_dir, project_dir)
        res = _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            install_parzival="true",
            stub_deploy=False,
            extra_bash=_FAIL_PACKAGE_COPY
            + '\nconfigure_parzival_env() { echo "configure_ran=1"; }\n',
        )
        assert "configure_ran=1" not in (res.stdout + res.stderr)

    def test_a_re_run_with_the_failure_removed_ends_with_a_working_agent(
        self, install_sh_no_main, dirs, tmp_path
    ):
        """Recoverable, end to end. condition is deliberately NOT asserted on the
        re-run: the ruled option C (routed separately, not built here) changes
        what a two-argument write does to an existing partial.
        """
        install_dir, project_dir = dirs
        _seed_existing_install(install_dir, project_dir)
        first = _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            install_parzival="true",
            stub_deploy=False,
            extra_bash=_FAIL_PACKAGE_COPY,
        )
        assert first.returncode == 0, first.stdout + first.stderr
        _assert_record(_env_values(install_dir), "false", "failed", "partial")

        second = _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            install_parzival="true",
            stub_deploy=False,
        )
        assert second.returncode == 0, second.stdout + second.stderr
        _assert_working_agent(install_dir, project_dir, "recovery re-run")


class TestRetainedBackupsSurviveALaterRun:
    """A retained backup that a later run deletes is not a recovery copy.

    The backups used to be named with a $$ suffix and every run began by
    rm -rf'ing its own two paths, so a second run with the same PID deleted the
    directory the first run's report had just named -- and then reused the path.
    PIDs repeat when they wrap and in fresh PID namespaces.

    Both runs happen inside ONE bash process here, which shares $$ by
    construction. That reproduces PID reuse deterministically instead of waiting
    for a wrap, and it is why this test would have been RED under the old naming
    rather than merely flaky.
    """

    def test_a_second_run_in_the_same_process_neither_deletes_nor_reuses_them(
        self, install_sh_no_main, dirs, tmp_path
    ):
        install_dir, project_dir = dirs
        _seed_existing_install(install_dir, project_dir)
        res = _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            install_parzival="true",
            stub_deploy=False,
            extra_bash=_FAIL_PACKAGE_COPY + """
setup_parzival
_first_backups="$_PARZIVAL_STOP_BACKUPS"
echo "same_pid=$$"
unset -f cp
""",
            post_bash="""
while IFS= read -r _p; do
    [[ -n "$_p" ]] || continue
    if [[ -d "$_p" ]]; then echo "retained_survived=$_p"; else echo "retained_LOST=$_p"; fi
done <<< "$_first_backups"
""",
        )
        combined = res.stdout + res.stderr
        assert res.returncode == 0, combined
        assert "retained_survived=" in combined, combined
        assert "retained_LOST=" not in combined, combined


class TestAStopBeforeTheDestinationIsTouched:
    """The other kind of stop: $dst still holds what it held, so nothing is
    retained and the condition is the default one.
    """

    def test_a_failed_memory_backup_leaves_the_destination_untouched(
        self, install_sh_no_main, dirs, tmp_path
    ):
        install_dir, project_dir = dirs
        _seed_existing_install(install_dir, project_dir)
        res = _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            install_parzival="true",
            stub_deploy=False,
            extra_bash=_FAIL_MEMORY_BACKUP,
        )
        assert res.returncode == 0, res.stdout + res.stderr
        _assert_record(_env_values(install_dir), "false", "failed", "complete")
        note = project_dir / "_ai-memory" / "_memory" / "user-note.md"
        assert note.is_file(), "the operator's _memory/ must be untouched"
        assert note.read_text(encoding="utf-8") == "operator content\n"

    def test_td_537_the_memory_backup_does_not_leak(
        self, install_sh_no_main, dirs, tmp_path
    ):
        """TD-537. A successful mkdir followed by a failed cp -rp used to skip
        the cleanup silently -- and, because errexit is off in this function,
        used to fall through to rm -rf "$dst" and delete the only complete copy
        of the operator's _memory/. The sanctum twin is NOT asserted here: it was
        already unconditional at baseline, so a test there passes before the
        change and proves nothing.
        """
        install_dir, project_dir = dirs
        _seed_existing_install(install_dir, project_dir)
        _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            install_parzival="true",
            stub_deploy=False,
            extra_bash=_FAIL_MEMORY_BACKUP,
        )
        assert _backup_dirs(install_dir) == [], _backup_dirs(install_dir)

    def test_a_failed_sanctum_backup_also_removes_the_complete_memory_backup(
        self, install_sh_no_main, dirs, tmp_path
    ):
        """The sanctum backup runs after the _memory backup has finished, so a
        stop here leaves a COMPLETE backup on disk as well as the incomplete one.
        "No backup directory created by this run remains" covers both; reading
        the requirement as "remove the incomplete one" leaves the other behind.
        """
        install_dir, project_dir = dirs
        _seed_existing_install(install_dir, project_dir)
        res = _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            install_parzival="true",
            stub_deploy=False,
            extra_bash=_FAIL_SANCTUM_BACKUP,
        )
        assert res.returncode == 0, res.stdout + res.stderr
        _assert_record(_env_values(install_dir), "false", "failed", "complete")
        assert _backup_dirs(install_dir) == [], _backup_dirs(install_dir)
        assert (project_dir / "_ai-memory" / "_memory" / "user-note.md").is_file()


class TestTd819RefusesAnUnexpectedDestination:
    """TD-819. The guard was an EXISTENCE check, not a path-shape check, and
    AC-4 says fail CLOSED -- an unguarded recursive delete is the one operation
    that cannot. This story multiplies the blast radius, because on an update
    over a never-converted install $dst holds the operator's real _memory/ and
    sanctum/.

    The shape that actually goes wrong is PROJECT_PATH: install.sh silently falls
    back to the current directory when it cannot enter its target argument, which
    yields a RELATIVE path. It keeps prune_pov_shims' exit 1 rather than
    recording anything, because a destination of the wrong shape means
    PROJECT_PATH itself is wrong.
    """

    def test_a_relative_destination_is_refused_rather_than_deleted(
        self, install_sh_no_main, dirs, tmp_path
    ):
        install_dir, _ = dirs
        (install_dir / "_ai-memory" / "pov").mkdir(parents=True, exist_ok=True)
        relative_root = tmp_path / "relproj"
        (relative_root / "_ai-memory" / "_memory").mkdir(parents=True)
        (relative_root / "_ai-memory" / "_memory" / "user-note.md").write_text(
            "operator content\n", encoding="utf-8"
        )

        res = subprocess.run(
            [
                "bash",
                "-c",
                f"""
set -euo pipefail
cd "{tmp_path}"
export INSTALL_DIR="{install_dir}"
export PROJECT_PATH="relproj"
export NON_INTERACTIVE="true"
source "{install_sh_no_main}"
INSTALL_DIR="{install_dir}"
PROJECT_PATH="relproj"
NON_INTERACTIVE="true"
{_STUBS}
deploy_parzival_v2
""",
            ],
            capture_output=True,
            text=True,
            env=_bash_env(tmp_path),
        )
        combined = res.stdout + res.stderr
        assert res.returncode != 0, (
            "fail CLOSED: the run must not continue\n" + combined
        )
        assert "Refusing to rm -rf" in combined, combined
        assert (
            relative_root / "_ai-memory" / "_memory" / "user-note.md"
        ).is_file(), "the destination must not have been deleted"


class TestTheNewExitCodeIsAssertedDistinctly:
    """The enablement-record failure code is 3, not merely non-zero.

    Tasks 1-3 change which branches write the record, and therefore how many
    writes occur, so they change exit-3 reachability. A harness that buckets all
    non-zero exits together cannot see this and reports a regression as a generic
    failure.
    """

    def test_a_clean_converting_run_does_not_exit_3(
        self, install_sh_no_main, dirs, tmp_path
    ):
        """The negative half. Without it, "exit 3 on a record failure" is
        satisfied by exiting 3 always.
        """
        install_dir, project_dir = dirs
        res = _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            post_bash="parzival_record_status\n",
        )
        assert res.returncode == 0, res.stdout + res.stderr
        _assert_working_agent(install_dir, project_dir, "clean converting run")

    def test_a_failed_record_write_exits_3(self, install_sh_no_main, dirs, tmp_path):
        install_dir, project_dir = dirs
        res = _run(
            install_sh_no_main,
            install_dir,
            project_dir,
            tmp_path,
            # Fail ONLY the record's temp file. `mktemp -d` is left working
            # because deploy_parzival_v2 now uses it for the backups, and failing
            # that instead would produce a before-touch stop -- a different
            # event that happens to share an exit code.
            #
            # The test is on $1 being exactly the flag, NOT a `*-d*` glob over
            # "$*". The glob matched the TEMPLATE argument too, because pytest's
            # tmp_path here contains "-dev-", so the shadow forwarded every call
            # to the real mktemp, no write ever failed, and the test reported a
            # missing exit 3 that the installer was never asked to produce.
            extra_bash="""
mktemp() {
    if [[ "${1:-}" == "-d" ]]; then
        command mktemp "$@"
    else
        return 1
    fi
}
""",
            post_bash="parzival_record_status\n",
        )
        assert res.returncode == 3, (
            f"expected the distinct record-failure code 3, got {res.returncode}:\n"
            + res.stdout
            + res.stderr
        )


class TestTd734TheFullCopyToShimTransition:
    """Task 6 / TD-734. This story closes the "non-Parzival install" class by
    construction -- the leak's proposed gate becomes always-true -- so the record
    is dispositioned rather than re-fixed. What is genuinely new is the
    TRANSITION it creates, and nothing has ever run it: a project installed
    before the thin-shim model carries FULL copies of the POV skills under
    .claude/skills/, and every install now generates shims over them.

    THE STORY'S POPULATION FIGURE DOES NOT REPRODUCE, and the test is built on
    the measurement instead. The story says "9 unreconciled full copies". At
    7cc9a17 there are TWELVE POV skills under _ai-memory/pov/skills/, SIX of them
    also ship a .claude/skills/ copy, and all six of those are ALREADY thin shims
    -- so the shipped tree contains no full copy to reconcile at all. The hazard
    is therefore not in what ships; it is in what an OLDER install left on a
    project's disk, which is what this seeds.

    The path is also no longer the two functions the intake describes. There are
    three: deploy_ai_memory_skills (unconditional, first), deploy_parzival_shims
    (which prunes, but only inside .claude/agents/pov and .claude/commands/pov),
    and generate_parzival_skill_shims.
    """

    _SKILL = "aim-parzival-bootstrap"

    def _seed_and_run(self, install_sh_copy, install_dir, project_dir, tmp_path):
        # Shipped source: the thin-shim copy the installer deploys from.
        src_skill = install_dir / ".claude" / "skills" / self._SKILL
        src_skill.mkdir(parents=True)
        (src_skill / "SKILL.md").write_text(
            "---\nname: " + self._SKILL + "\n---\n\n# Shipped\n", encoding="utf-8"
        )

        # The project as an OLDER install left it: a genuine full copy, with
        # support files beside the SKILL.md.
        old = project_dir / ".claude" / "skills" / self._SKILL
        (old / "scripts").mkdir(parents=True)
        (old / "SKILL.md").write_text(
            "---\nname: " + self._SKILL + "\n---\n\n# Full copy, pre-shim\n"
            "Every step inlined here.\n",
            encoding="utf-8",
        )
        (old / "scripts" / "legacy.py").write_text(
            "# shipped with the full copy\n", encoding="utf-8"
        )

        # The deployed pov tree the generated shim will point at.
        pov = project_dir / "_ai-memory" / "pov" / "skills" / self._SKILL
        pov.mkdir(parents=True)
        (pov / "SKILL.md").write_text(
            "---\nname: " + self._SKILL + "\ndescription: real\n---\n\n# Real skill\n",
            encoding="utf-8",
        )

        return subprocess.run(
            [
                "bash",
                "-c",
                f"""
set -euo pipefail
export INSTALL_DIR="{install_dir}"
export PROJECT_PATH="{project_dir}"
export NON_INTERACTIVE="true"
source "{install_sh_copy}"
INSTALL_DIR="{install_dir}"
PROJECT_PATH="{project_dir}"
NON_INTERACTIVE="true"
deploy_ai_memory_skills
generate_parzival_skill_shims
""",
            ],
            capture_output=True,
            text=True,
            env=_bash_env(tmp_path),
        )

    def test_the_end_state_is_a_shim_pointing_at_a_file_that_exists(
        self, install_sh_no_main, dirs, tmp_path
    ):
        """The load-bearing coherence property. A generated shim whose LOAD path
        names a missing file is a skill that is discoverable and unusable, which
        is worse than one that is absent.
        """
        install_dir, project_dir = dirs
        res = self._seed_and_run(install_sh_no_main, install_dir, project_dir, tmp_path)
        assert res.returncode == 0, res.stdout + res.stderr

        shim = project_dir / ".claude" / "skills" / self._SKILL / "SKILL.md"
        text = shim.read_text(encoding="utf-8")
        assert "**LOAD**" in text, f"the full copy was not replaced by a shim:\n{text}"
        assert "Full copy, pre-shim" not in text, text

        rel = text.split("`")[1]
        assert (project_dir / rel).is_file(), f"shim points at a missing file: {rel}"

    def test_the_old_full_copys_support_files_are_left_behind(
        self, install_sh_no_main, dirs, tmp_path
    ):
        """PINNED AS THE OBSERVED END STATE, NOT ASSERTED AS DESIRABLE.

        For a skill with no canonical entry -- which is every POV skill -- the
        deploy is mkdir -p followed by cp -r, with no rm -rf of the target. Only
        files the source also carries are overwritten, so SKILL.md becomes a shim
        while the old copy's scripts/ survives beside it. The surviving file is a
        stale duplicate of one that also lives under the deployed pov tree, so a
        skill resolving a script path relative to its own directory can reach the
        stale one.

        This story's Task 6 is to TEST the transition, not to re-fix TD-734, so
        the behaviour is pinned here and reported rather than changed. If it is
        ever fixed, this test is the one that should fail and be updated.
        """
        install_dir, project_dir = dirs
        res = self._seed_and_run(install_sh_no_main, install_dir, project_dir, tmp_path)
        assert res.returncode == 0, res.stdout + res.stderr

        orphan = (
            project_dir / ".claude" / "skills" / self._SKILL / "scripts" / "legacy.py"
        )
        assert orphan.is_file(), (
            "the observed end state has changed: the pre-shim full copy's support "
            "files used to survive the transition. If this was fixed deliberately, "
            "update this test and TD-734's disposition together."
        )

    def test_the_shipped_tree_carries_no_full_copy_of_a_pov_skill(self):
        """The population claim, re-derived rather than quoted.

        Every POV skill that also ships a .claude/skills/ copy must already be a
        thin shim. If a full copy ever ships again, the transition above stops
        being only a legacy concern and starts happening on fresh installs.
        """
        root = _INSTALL_SH.parent.parent
        pov_skills = sorted(
            p.name for p in (root / "_ai-memory/pov/skills").iterdir() if p.is_dir()
        )
        assert pov_skills, "no POV skills found -- the derivation has rotted"
        offenders = []
        for name in pov_skills:
            shipped = root / ".claude" / "skills" / name / "SKILL.md"
            if shipped.is_file() and "**LOAD**" not in shipped.read_text(
                encoding="utf-8"
            ):
                offenders.append(name)
        assert not offenders, f"these ship a full copy rather than a shim: {offenders}"
