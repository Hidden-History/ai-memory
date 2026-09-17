"""Install tests for Module-granularity BMAD detection (Story 1.5, AD-33).

The installer reports whether the BMAD **BMM Module** is available to the target
project, at Module granularity, and never changes the install's exit status for it.

Three states are required, and they are three — not "present/absent":

  * ``bmad-absent``  — no BMAD root under the project path                  (AC-1)
  * ``bmm-absent``   — BMAD root present, the BMM Module is not             (AC-2)
  * ``bmm-present``  — the BMM Module is installed                          (AC-3)

A **fourth** state is reported for evidence that exists but cannot be read:

  * ``bmad-indeterminate`` — the BMAD root is there and cannot be traversed, or no
    project path was supplied. ``[[ -d ]]`` succeeds on a mode-000 directory while
    every test beneath it fails with ``EACCES``, which ``[[ ]]`` cannot distinguish
    from ``ENOENT`` — so falling through to ``bmm-absent`` would tell an operator
    whose machine *has* BMM that BMM is absent. ``AD-33`` enumerates three states
    and does not classify this one; under ``AD-24`` that is a spine defect to be
    classified rather than an implementer's pick. It was escalated and ruled on:
    **report it, never abort.** These tests assert the reported state directly —
    the round-1 suite deliberately declined to, which is what let the silent
    misclassification ship.

Two surfaces are covered:

  1. ``detect_bmad_module_state()`` — resolves exactly one of the three states and
     writes it to stdout. It emits no operator-facing output, so state resolution
     is assertable without capturing a message.
  2. ``report_bmad_module_state()`` — maps a state to the operator-facing line.
     Absence is reported; presence is silent on a normal run (AC-3).

**AC-4 is asserted against the declared design.** ``install.sh`` implements
*design A* of the two the story allows: one function, state on stdout,
``return 0`` always. For design A the AC-4 guarantee lives in the function's
**return discipline**, not in the call-site shape — a call site is an assignment
by construction there, so asserting its shape would prove nothing. These tests
therefore assert the return status directly, in every state including unreadable
evidence, and additionally assert the call site is not a bare consumption.

Harness: the repo's ``install_sh_no_main`` fixture, copied into this module as a
per-module fixture exactly as the other install-test modules do (it is not a
``conftest.py`` fixture and is not imported across modules). It copies the real
``install.sh`` minus its final ``main "$@"`` line and sources that copy, so the
real function bodies execute. A full ``bash install.sh`` subprocess would require
performing a real install to reach these functions, and no live system is
touched by this suite.

Declared exemption set (AD-20a) — trees the detector must **not** report as
``bmm-absent``:

  * ``EXEMPT_SIBLING_OUTPUT_TREE`` — a project carrying a similarly-named output
    tree (``_bmad-output/``) but no BMAD root. This is not a near-miss in theory:
    the repository this installer ships from carries exactly that directory.
  * ``EXEMPT_NESTED_BMAD_ROOT`` — a BMAD root that exists only deeper in the
    tree (``vendor/_bmad/``). Detection resolves relative to the project path it
    is given (N-8), so a nested root belongs to a different project.
  * ``EXEMPT_MODULE_INSTALLED`` — a project with the BMM Module installed. The
    positive direction of the pair: the state the detector must not mistake for
    the defect it reports.

Synthetic identifiers throughout. The one live name used is the literal ``bmm``,
which is the Module under test and is named by the requirement itself.
"""

import ast
import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
_INSTALL_SH = _SCRIPTS_DIR / "install.sh"
_INSTALL_MD = Path(__file__).parent.parent / "INSTALL.md"

# AD-20a declared exemption set — see module docstring.
EXEMPT_SIBLING_OUTPUT_TREE = "_bmad-output"
EXEMPT_NESTED_BMAD_ROOT = "vendor/_bmad"
EXEMPT_MODULE_INSTALLED = "_bmad/bmm/config.yaml"

STATE_BMAD_ABSENT = "bmad-absent"
STATE_BMM_ABSENT = "bmm-absent"
STATE_BMM_PRESENT = "bmm-present"
STATE_BMAD_INDETERMINATE = "bmad-indeterminate"

# Harness isolation. Every subprocess here sources a copy of the real installer,
# so it runs with an environment BUILT from these keys, never inherited: an
# inherited one carries the operator's install binding, live credentials and a
# PATH on which the real `docker` resolves.
_HARNESS_ENV_KEYS = frozenset({"PATH", "HOME", "LOG_LEVEL"})
# What sourcing the stripped copy and running the two functions under test calls
# beyond bash builtins: install.sh's top-level preamble (`dirname`, `basename`,
# `sed`, `tr`). `git` is deliberately absent — the preamble's one `git` call is
# `|| true`-guarded with stderr discarded, so leaving it off PATH changes nothing.
_HARNESS_TOOLS = ("bash", "basename", "dirname", "sed", "tr")
_CREDENTIAL_NAME = re.compile(
    r"KEY|TOKEN|SECRET|PASS|CREDENTIAL|AUTH|COOKIE|(^|_)PAT($|_)", re.IGNORECASE
)
_LIVE_COMMANDS = ("docker", "install.sh", "stack.sh")


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


_harness = {}


@pytest.fixture(scope="module", autouse=True)
def _harness_sandbox(tmp_path_factory):
    """Build the curated PATH and the empty HOME that `_env()` hands out.

    PATH is one directory holding a link to each of `_HARNESS_TOOLS` and nothing
    else, so no other command — `docker` above all — can resolve. The tools are
    looked up in the system directories, not on the runner's PATH.
    """
    root = tmp_path_factory.mktemp("bmad-harness")
    bin_dir = root / "bin"
    bin_dir.mkdir()
    for tool in _HARNESS_TOOLS:
        real = shutil.which(tool, path="/usr/bin:/bin")
        if real is None:
            pytest.fail(f"harness tool {tool!r} not found in /usr/bin or /bin")
        (bin_dir / tool).symlink_to(real)
    home = root / "home"
    home.mkdir()
    _harness.update(path=str(bin_dir), home=str(home))
    yield
    _harness.clear()


def _env(log_level: str = "info") -> dict:
    """The environment for every harness subprocess, built — never inherited.

    ``subprocess.run`` inherits ``os.environ`` by default, and that carries the
    operator's install binding, live credentials and a PATH that resolves the
    real ``docker``. Only ``_HARNESS_ENV_KEYS`` are set. ``LOG_LEVEL`` is pinned
    because a runner with ``LOG_LEVEL=debug`` exported would flip the AC-3
    silence test. ``HOME`` is pinned because install.sh falls back to
    ``$HOME/.ai-memory`` when ``AI_MEMORY_INSTALL_DIR`` is unset.
    """
    assert _harness, "harness sandbox not set up"
    return {"PATH": _harness["path"], "HOME": _harness["home"], "LOG_LEVEL": log_level}


def _project(tmp_path, name: str, *relative_dirs: str) -> Path:
    """Build a synthetic project tree, creating each relative directory under it."""
    project = tmp_path / name
    project.mkdir()
    for relative in relative_dirs:
        (project / relative).mkdir(parents=True)
    return project


def _module_config(project: Path) -> Path:
    """Write the BMM Module's own config — the discriminator the detector reads."""
    config = project / "_bmad" / "bmm" / "config.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("module_name: sample-module\n", encoding="utf-8")
    return config


def _detect(install_sh_copy: Path, project: Path) -> subprocess.CompletedProcess:
    """Source install.sh and resolve the state for `project`, reporting the status.

    Runs under the same `set -euo pipefail` the real script runs under, and echoes
    the detector's return status on a trailing line so AC-4 can be asserted
    directly rather than inferred from the call site. The capture is a plain
    assignment, never `local`/`declare` — a declaration command's exit status is
    its own, which would swallow the very non-zero return AC-4 exists to catch.

    `|| rc=$?` is load-bearing and was absent in round 1. Without it, `set -e`
    aborts the shell *at the assignment* when the detector returns non-zero, so
    `RC=` is either printed as `RC=0` or never printed at all — making an
    `"RC=0" in stdout` assertion a tautology that cannot observe the failure it
    names. With it, a non-zero return is captured and reported instead of being
    fatal, so `RC=` carries real information.
    """
    bash_cmd = f"""
set -euo pipefail
source "{install_sh_copy}"
rc=0
state=$(detect_bmad_module_state "{project}") || rc=$?
echo "STATE=$state"
echo "RC=$rc"
echo "REACHED_END=yes"
"""
    return subprocess.run(
        ["bash", "-c", bash_cmd], capture_output=True, text=True, env=_env()
    )


def _state_of(result: subprocess.CompletedProcess) -> str:
    for line in result.stdout.splitlines():
        if line.startswith("STATE="):
            return line[len("STATE=") :].strip()
    raise AssertionError(
        f"No STATE= line in detector output.\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def _report(
    install_sh_copy: Path, project: Path, out_file: Path, log_level: str = "info"
) -> subprocess.CompletedProcess:
    """Run the reporter with its whole output isolated into `out_file`.

    Sourcing the script emits nothing today, but AC-3's assertion is about what
    the reporting call emits, so the call's own streams are captured separately
    rather than diffed out of the surrounding run.
    """
    bash_cmd = f"""
set -euo pipefail
source "{install_sh_copy}"
report_bmad_module_state "{project}" > "{out_file}" 2>&1
echo "REACHED_END=yes"
"""
    return subprocess.run(
        ["bash", "-c", bash_cmd], capture_output=True, text=True, env=_env(log_level)
    )


@pytest.fixture
def unreadable_bmad_root(tmp_path):
    """A BMAD root that exists but cannot be traversed, restored on teardown.

    FAILS — does not skip — when the running user can traverse it regardless of
    mode (root, or a filesystem that does not enforce POSIX permissions).

    A skip here is silently green, and this repository lives on a filesystem that
    does not enforce POSIX modes: a run with TMPDIR pointed at it would skip both
    unreadable-evidence tests and report success. That is the same class of defect
    these tests exist to catch, so the unmeasurable case is loud.
    """
    project = _project(tmp_path, "unreadable_project")
    root = project / "_bmad"
    root.mkdir()
    (root / "bmm").mkdir()
    root.chmod(0o000)
    try:
        still_readable = (root / "bmm").is_dir()
    except PermissionError:
        still_readable = False
    if still_readable:
        root.chmod(0o755)
        pytest.fail(
            "cannot construct unreadable evidence: this user or filesystem does not "
            f"enforce directory permissions at {root}. Run as a non-root user with "
            "TMPDIR on a POSIX-mode-enforcing filesystem (ext4), or these AC-4 "
            "assertions measure nothing."
        )
    yield project
    root.chmod(0o755)


@pytest.fixture
def unreadable_module_dir(tmp_path):
    """A readable BMAD root whose BMM Module directory cannot be traversed.

    One level deeper than `unreadable_bmad_root`: the root answers, the Module
    does not. Reported for the same reason — a negative that means "could not
    look" is not evidence of absence.

    The Module's config IS written before the mode change, and that is
    load-bearing twice over. It makes the fail-loud guard below reachable: the
    guard probes `config.yaml`, and a path that is never created is
    `is_file() == False` for every user on every filesystem, so the guard could
    not fire and the unmeasurable case was silently green. It also makes this the
    one fixture where BMM is genuinely INSTALLED and its evidence unreadable —
    the tree the declared AC-3 exception is about.
    """
    project = _project(tmp_path, "unreadable_module_project")
    module = project / "_bmad" / "bmm"
    module.mkdir(parents=True)
    (module / "config.yaml").write_text(
        "module_name: sample-module\n", encoding="utf-8"
    )
    module.chmod(0o000)
    try:
        still_readable = (module / "config.yaml").is_file()
    except PermissionError:
        still_readable = False
    if still_readable:
        module.chmod(0o755)
        pytest.fail(
            "cannot construct an unreadable Module directory: this user or "
            f"filesystem does not enforce directory permissions at {module}."
        )
    yield project
    module.chmod(0o755)


@pytest.fixture
def search_only_bmad_root(tmp_path):
    """A `_bmad` root that is searchable (`-x`) but not listable (`-r`), with the
    BMM Module present underneath it — restored on teardown.

    The detector never lists a directory; it only stats named children, which
    POSIX resolves with search permission alone. A search-only root is therefore
    fully resolvable, and reporting anything other than the real state on one is
    a reachable `AC-3` violation, not an over-strict guard.

    FAILS — does not skip — when the running user can list the directory
    regardless of mode (root, or a filesystem that does not enforce POSIX
    permissions), for the same reason `unreadable_bmad_root` does: a skip here
    would silently stop measuring the property this fixture exists to prove.
    """
    project = _project(tmp_path, "search_only_project")
    _module_config(project)
    root = project / "_bmad"
    root.chmod(0o111)
    try:
        still_listable = list(root.iterdir())
    except PermissionError:
        still_listable = None
    if still_listable is not None:
        root.chmod(0o755)
        pytest.fail(
            "cannot construct a search-only, non-listable directory: this user "
            f"or filesystem does not enforce directory permissions at {root}."
        )
    yield project
    root.chmod(0o755)


@pytest.fixture
def unsearchable_project_path(tmp_path):
    """A project directory that cannot be searched, with BMM installed inside it.

    `_bmad` is a REAL directory here, and that is the point: `-L` on it is false,
    so a guard written against symlinks alone is blind to this tree. `-x` on the
    project path is what stays observable — it needs only search permission on the
    project path's own parent.

    FAILS — does not skip — on a user or filesystem that does not enforce
    directory permissions, for the same reason `unreadable_bmad_root` does.
    """
    project = _project(tmp_path, "unsearchable_project")
    _module_config(project)
    project.chmod(0o000)
    try:
        still_reachable = (project / "_bmad").is_dir()
    except PermissionError:
        still_reachable = False
    if still_reachable:
        project.chmod(0o755)
        pytest.fail(
            "cannot construct an unsearchable project path: this user or "
            f"filesystem does not enforce directory permissions at {project}."
        )
    yield project
    project.chmod(0o755)


@pytest.fixture
def symlinked_root_with_unresolvable_target(tmp_path):
    """`_bmad` symlinked to a shared install whose parent cannot be searched.

    The shared-install layout the detector's own header blesses — one BMAD tree
    linked into several projects — with the shared tree under a restricted
    parent. The link itself is fully visible (`-L` true); its target is not
    (`-d` false). BMM is genuinely installed on the other end.

    FAILS — does not skip — on a non-enforcing user or filesystem.
    """
    project = _project(tmp_path, "symlinked_root_project")
    shared = tmp_path / "shared_install"
    real_root = shared / "_bmad"
    (real_root / "bmm").mkdir(parents=True)
    (real_root / "bmm" / "config.yaml").write_text(
        "module_name: sample-module\n", encoding="utf-8"
    )
    (project / "_bmad").symlink_to(real_root)
    shared.chmod(0o000)
    try:
        still_reachable = (project / "_bmad").is_dir()
    except PermissionError:
        still_reachable = False
    if still_reachable:
        shared.chmod(0o755)
        pytest.fail(
            "cannot construct an unresolvable symlink target: this user or "
            f"filesystem does not enforce directory permissions at {shared}."
        )
    yield project
    shared.chmod(0o755)


@pytest.fixture
def symlinked_module_with_unresolvable_target(tmp_path):
    """`_bmad/bmm` symlinked to a shared install whose parent cannot be searched.

    The Module-level twin of `symlinked_root_with_unresolvable_target`: here the
    root is a real, searchable directory, and the Module itself is the
    shared-install link. The link is fully visible (`-L` true); its target is not
    (`-d` false). BMM is genuinely installed on the other end.

    FAILS — does not skip — on a non-enforcing user or filesystem.
    """
    project = _project(tmp_path, "symlinked_module_project", "_bmad")
    shared = tmp_path / "shared_module_install"
    real_module = shared / "bmm"
    real_module.mkdir(parents=True)
    (real_module / "config.yaml").write_text(
        "module_name: sample-module\n", encoding="utf-8"
    )
    (project / "_bmad" / "bmm").symlink_to(real_module)
    shared.chmod(0o000)
    try:
        still_reachable = (project / "_bmad" / "bmm").is_dir()
    except PermissionError:
        still_reachable = False
    if still_reachable:
        shared.chmod(0o755)
        pytest.fail(
            "cannot construct an unresolvable symlink target: this user or "
            f"filesystem does not enforce directory permissions at {shared}."
        )
    yield project
    shared.chmod(0o755)


@pytest.fixture
def symlinked_module_config_with_unresolvable_target(tmp_path):
    """`_bmad/bmm/config.yaml` symlinked to a file whose parent cannot be searched.

    One node further than `symlinked_module_with_unresolvable_target`: here the
    Module directory itself is real, and only its `config.yaml` is the
    shared-install link — the per-file variant of the same layout. The link is
    fully visible (`-L` true); its target is not (`-e` false). The target holds
    real, non-empty content, so BMM is genuinely installed on the other end.

    FAILS — does not skip — on a non-enforcing user or filesystem.
    """
    project = _project(tmp_path, "symlinked_module_config_project", "_bmad/bmm")
    shared = tmp_path / "shared_config_install"
    shared.mkdir()
    real_config = shared / "config.yaml"
    real_config.write_text("module_name: sample-module\n", encoding="utf-8")
    (project / "_bmad" / "bmm" / "config.yaml").symlink_to(real_config)
    shared.chmod(0o000)
    try:
        still_reachable = (project / "_bmad" / "bmm" / "config.yaml").is_file()
    except PermissionError:
        still_reachable = False
    if still_reachable:
        shared.chmod(0o755)
        pytest.fail(
            "cannot construct an unresolvable symlink target: this user or "
            f"filesystem does not enforce directory permissions at {shared}."
        )
    yield project
    shared.chmod(0o755)


class TestHarnessEnvironmentIsIsolated:
    """The controls every other test here depends on — checked without running any.

    Nothing in this class sources the installer copy. Its assertions print key
    NAMES only, never values, because the environment it inspects is exactly the
    one that must not carry credentials.
    """

    def test_harness_environment_is_built_from_the_allowlist(self):
        keys = sorted(_env())

        assert "AI_MEMORY_INSTALL_DIR" not in keys
        assert not [k for k in keys if _CREDENTIAL_NAME.search(k)]
        assert set(keys) <= _HARNESS_ENV_KEYS, sorted(set(keys) - _HARNESS_ENV_KEYS)

    def test_harness_path_resolves_no_live_command(self):
        path = _env()["PATH"]
        resolved = [c for c in _LIVE_COMMANDS if shutil.which(c, path=path)]

        assert not resolved, f"harness PATH resolves {resolved}"
        entries = path.split(os.pathsep)
        assert len(entries) == 1, f"harness PATH has {len(entries)} entries, not 1"
        assert sorted(p.name for p in Path(entries[0]).iterdir()) == sorted(
            _HARNESS_TOOLS
        )

    def test_harness_home_is_not_an_install_root(self):
        """Removing AI_MEMORY_INSTALL_DIR alone is not isolation.

        install.sh's default is `${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}`, so
        with the key gone a real HOME resolves the operator's live install. HOME
        must be pinned too, and the pinned one must hold no install.
        """
        home = Path(_env()["HOME"])

        assert home != Path.home()
        assert not (home / ".ai-memory").exists()

    def test_every_harness_subprocess_uses_the_built_environment(self):
        """An allowlisted `_env()` protects nothing a call site does not pass."""
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        runs = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and ast.unparse(node.func) in ("subprocess.run", "subprocess.Popen")
        ]
        unguarded = [
            node.lineno
            for node in runs
            if not any(
                kw.arg == "env"
                and isinstance(kw.value, ast.Call)
                and ast.unparse(kw.value.func) == "_env"
                for kw in node.keywords
            )
        ]

        assert runs, "found no subprocess call to check"
        assert not unguarded, f"subprocess calls without env=_env(...): {unguarded}"


class TestDetectorResolvesThreeStates:
    """AC-1, AC-2, AC-3 — three distinct states, not present/absent."""

    def test_no_bmad_at_all_resolves_bmad_absent(self, install_sh_no_main, tmp_path):
        """AC-1: a repository with no BMAD at all resolves the named absent state."""
        project = _project(tmp_path, "no_bmad_project", "docs")

        result = _detect(install_sh_no_main, project)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMAD_ABSENT

    def test_nonexistent_project_path_still_resolves_bmad_absent(
        self, install_sh_no_main, tmp_path
    ):
        """AC-1: a path that is not there was LOOKED at, and nothing was found.

        The guard that stops an unsearchable project path being reported absent
        must not swallow this one with it: here the project path's own parent is
        searchable, so the negative is ENOENT and `bmad-absent` is the honest
        answer. This is the control on that fix, not a restatement of AC-1.
        """
        result = _detect(install_sh_no_main, tmp_path / "no_such_project")

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMAD_ABSENT

    def test_root_symlink_to_a_regular_file_resolves_bmad_absent(
        self, install_sh_no_main, tmp_path
    ):
        """A `_bmad` symlink that RESOLVES to a non-directory is absent, not unknown.

        The guard that reports an unresolvable `_bmad` symlink as indeterminate
        must not swallow a symlink that resolved perfectly well: here we looked,
        and what is there is not a BMAD root. Reporting "unknown" would answer
        indeterminate for this and absent for a bare regular file at the same
        path — the identical operator situation getting opposite answers, which
        is the defect that guard exists to remove, one node type over.
        """
        target = tmp_path / "not_a_directory"
        target.write_text("x", encoding="utf-8")
        project = _project(tmp_path, "symlink_to_file_project")
        (project / "_bmad").symlink_to(target)

        result = _detect(install_sh_no_main, project)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMAD_ABSENT

    def test_root_symlink_to_a_non_regular_file_resolves_bmad_absent(
        self, install_sh_no_main, tmp_path
    ):
        """Resolution succeeding, not regular-file-ness, is what makes it absent.

        `/dev/null` is a character device: it resolves, so we looked and it is
        not a BMAD root. This is the case that separates the shipped guard from
        a `-f`-based one — `-f` is false on a device, a FIFO and a socket, so a
        guard written as `-L && ! -f` reports "unknown" for all three when the
        target resolved perfectly well. `-e` asks the question the design's
        standard actually asks. `/dev/null` is used rather than a constructed
        FIFO or socket so the test needs no filesystem capability of its own.
        """
        project = _project(tmp_path, "symlink_to_device_project")
        (project / "_bmad").symlink_to("/dev/null")

        result = _detect(install_sh_no_main, project)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMAD_ABSENT

    def test_module_symlink_to_a_regular_file_resolves_bmm_absent(
        self, install_sh_no_main, tmp_path
    ):
        """The Module-depth twin of `test_root_symlink_to_a_regular_file_resolves_bmad_absent`.

        Pins the `! -e` conjunct at `_bmad/bmm`: mirrors the root guard's own
        `-L`/`! -e` limb, so it needs the same two-sided pin the root guard has.
        Without this test, deleting `! -e` from the module guard — leaving `-L`
        alone — still passes every other test in this module, because every
        other `_bmad/bmm` symlink fixture is dangling (`-e` false). Here the
        symlink RESOLVES, so `-L` alone would wrongly answer indeterminate.
        """
        target = tmp_path / "not_a_directory"
        target.write_text("x", encoding="utf-8")
        project = _project(tmp_path, "module_symlink_to_file_project", "_bmad")
        (project / "_bmad" / "bmm").symlink_to(target)

        result = _detect(install_sh_no_main, project)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMM_ABSENT

    def test_module_symlink_to_a_non_regular_file_resolves_bmm_absent(
        self, install_sh_no_main, tmp_path
    ):
        """The Module-depth twin of `test_root_symlink_to_a_non_regular_file_resolves_bmad_absent`.

        `/dev/null` resolves, so `_bmad/bmm` was looked at and is not a Module
        directory. Rules out a `-L && ! -f` narrowing at this node the same way
        the root-level counterpart does: `-f` is false on a device too, so that
        narrower guard would also misreport this resolved case as indeterminate.
        """
        project = _project(tmp_path, "module_symlink_to_device_project", "_bmad")
        (project / "_bmad" / "bmm").symlink_to("/dev/null")

        result = _detect(install_sh_no_main, project)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMM_ABSENT

    def test_config_symlink_to_an_empty_regular_file_resolves_bmm_absent(
        self, install_sh_no_main, tmp_path
    ):
        """The config-depth twin of `test_root_symlink_to_a_regular_file_resolves_bmad_absent`.

        Pins the `! -e` conjunct at `_bmad/bmm/config.yaml`: without this test,
        deleting `! -e` from the config guard — leaving `-L` alone — still passes
        every other test in this module, because every other `config.yaml`
        symlink fixture is dangling (`-e` false). Here the symlink RESOLVES, so
        `-L` alone would wrongly answer indeterminate.

        The target is EMPTY, not merely a regular file: the presence check
        (`-f && -s`) runs before either indeterminate guard and follows symlinks,
        so a symlink resolving to a NON-EMPTY regular file is legitimately
        `bmm-present` (the shared-install case) rather than the node this test
        pins — a non-empty target here would test the presence check, not this
        guard's `! -e` conjunct.
        """
        target = tmp_path / "not_a_config"
        target.write_text("", encoding="utf-8")
        project = _project(
            tmp_path, "config_symlink_to_empty_file_project", "_bmad/bmm"
        )
        (project / "_bmad" / "bmm" / "config.yaml").symlink_to(target)

        result = _detect(install_sh_no_main, project)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMM_ABSENT

    def test_config_symlink_to_a_non_regular_file_resolves_bmm_absent(
        self, install_sh_no_main, tmp_path
    ):
        """The config-depth twin of `test_root_symlink_to_a_non_regular_file_resolves_bmad_absent`.

        `/dev/null` resolves, so `_bmad/bmm/config.yaml` was looked at and is not
        a usable config. Rules out a `-L && ! -f` narrowing at this node for the
        same reason the root- and module-depth counterparts do.
        """
        project = _project(tmp_path, "config_symlink_to_device_project", "_bmad/bmm")
        (project / "_bmad" / "bmm" / "config.yaml").symlink_to("/dev/null")

        result = _detect(install_sh_no_main, project)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMM_ABSENT

    def test_bmad_root_without_module_resolves_bmm_absent(
        self, install_sh_no_main, tmp_path
    ):
        """AC-2: BMAD present, BMM absent is its own state — the middle one."""
        project = _project(
            tmp_path,
            "partial_bmad_project",
            "_bmad/sample-module-one",
            "_bmad/sample-module-two",
        )
        (project / "_bmad" / "config.yaml").write_text(
            "sample-module-one:\n  name: Sample Module One\n", encoding="utf-8"
        )

        result = _detect(install_sh_no_main, project)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMM_ABSENT

    def test_empty_module_directory_is_not_an_installed_module(
        self, install_sh_no_main, tmp_path
    ):
        """AC-2: the Module claim is made on the Module's own config, not a bare dir."""
        project = _project(tmp_path, "empty_module_project", "_bmad/bmm")

        result = _detect(install_sh_no_main, project)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMM_ABSENT

    def test_empty_module_config_is_not_an_installed_module(
        self, install_sh_no_main, tmp_path
    ):
        """A zero-byte config records no version, so it certifies no Module.

        `[[ -f ]]` is true on a zero-byte file, so `-f` would certify a
        half-written BMAD install as present and Story 1.6 would then read nothing
        out of it. `-s` is the test that matches the discriminator's stated intent.
        """
        project = _project(tmp_path, "empty_config_project", "_bmad/bmm")
        (project / "_bmad" / "bmm" / "config.yaml").write_text("", encoding="utf-8")

        result = _detect(install_sh_no_main, project)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMM_ABSENT

    def test_module_config_as_a_directory_is_not_an_installed_module(
        self, install_sh_no_main, tmp_path
    ):
        """`-s` alone does not assert regular-file-ness — a directory has nonzero
        apparent size, so a `config.yaml` that is itself a directory (a botched
        merge, an aborted extraction, a `mkdir -p` typo) must not certify the
        Module. Story 1.6 is the stated future reader of this path; a directory
        certified `bmm-present` here becomes an `EISDIR` there.
        """
        project = _project(tmp_path, "dir_as_config_project", "_bmad/bmm")
        (project / "_bmad" / "bmm" / "config.yaml").mkdir()

        result = _detect(install_sh_no_main, project)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMM_ABSENT

    def test_bmad_root_as_a_regular_file_is_not_a_bmad_root(
        self, install_sh_no_main, tmp_path
    ):
        """A `_bmad` that is a file is read, not misread: there is no BMAD root.

        This is deliberately `bmad-absent` and not `bmad-indeterminate`. The
        evidence was readable; it simply is not a BMAD installation. Indeterminate
        is reserved for evidence that could not be READ, and widening it to cover
        "read fine, not a BMAD root" would drain the distinction of meaning.
        """
        project = _project(tmp_path, "file_root_project")
        (project / "_bmad").write_text("not a directory\n", encoding="utf-8")

        result = _detect(install_sh_no_main, project)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMAD_ABSENT

    def test_module_config_present_resolves_bmm_present(
        self, install_sh_no_main, tmp_path
    ):
        """AC-3: the Module's own config is the evidence for BMM present."""
        project = _project(tmp_path, "full_bmad_project")
        _module_config(project)

        result = _detect(install_sh_no_main, project)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMM_PRESENT

    def test_search_only_root_with_bmm_present_resolves_bmm_present(
        self, install_sh_no_main, search_only_bmad_root
    ):
        """AC-3: search-only (no list) permission must not manufacture indeterminate.

        A `_bmad` root at mode `0111` — searchable, not listable, the ordinary
        hardening of a shared-install layout this function's own header endorses
        — is fully resolvable via the named lookups the detector actually
        performs. Reporting `bmad-indeterminate` here fires a warning on a
        repository with BMM present, which `AC-3` forbids outright.
        """
        result = _detect(install_sh_no_main, search_only_bmad_root)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMM_PRESENT

    def test_root_config_naming_other_modules_does_not_decide_bmm(
        self, install_sh_no_main, tmp_path
    ):
        """The BMAD root config is not a module registry — reading it inverts AC-2.

        A root config naming only other modules, on a tree that *has* BMM, must
        still resolve `bmm-present`. A detector that parsed the root config would
        report the Module dark on a machine where it is lit.
        """
        project = _project(tmp_path, "root_config_project")
        _module_config(project)
        (project / "_bmad" / "config.yaml").write_text(
            "sample-module-one:\n  name: Sample Module One\n", encoding="utf-8"
        )

        result = _detect(install_sh_no_main, project)

        assert _state_of(result) == STATE_BMM_PRESENT


class TestReportedMessages:
    """AC-1, AC-2, AC-3 — what the operator actually sees in each state."""

    def test_bmad_absent_is_a_named_report_not_a_silence(
        self, install_sh_no_main, tmp_path
    ):
        """AC-1: absence is a named state. Reporting nothing does not satisfy it."""
        project = _project(tmp_path, "no_bmad_project")
        out_file = tmp_path / "out-absent.txt"

        result = _report(install_sh_no_main, project, out_file)
        output = out_file.read_text(encoding="utf-8")

        assert result.returncode == 0, result.stderr
        assert "BMAD absent" in output, output

    def test_bmm_absent_message_names_bmm_as_the_required_module(
        self, install_sh_no_main, tmp_path
    ):
        """AC-2: the message names BMM. "BMAD is incomplete" does not satisfy it."""
        project = _project(tmp_path, "partial_bmad_project", "_bmad/sample-module-one")
        out_file = tmp_path / "out-bmm-absent.txt"

        result = _report(install_sh_no_main, project, out_file)
        output = out_file.read_text(encoding="utf-8")

        assert result.returncode == 0, result.stderr
        # "BMM" and "Module" both appear in the bmad-absent message too, so
        # asserting only those would pass against a detector that collapsed AC-2
        # into AC-1. Assert the two things AC-2 actually requires: that BMM is
        # reported MISSING, and that it is named as the required Module.
        assert "BMM absent" in output, output
        assert "BMM is the required Module" in output, output
        assert "BMAD absent" not in output, output

    def test_bmm_absent_message_is_distinguishable_from_bmad_absent(
        self, install_sh_no_main, tmp_path
    ):
        """AC-2: told "BMAD absent" on a machine with most of BMAD is the defect."""
        partial = _project(tmp_path, "partial_project", "_bmad/sample-module-one")
        absent = _project(tmp_path, "absent_project")
        partial_out = tmp_path / "partial.txt"
        absent_out = tmp_path / "absent.txt"

        _report(install_sh_no_main, partial, partial_out)
        _report(install_sh_no_main, absent, absent_out)

        partial_text = partial_out.read_text(encoding="utf-8")
        absent_text = absent_out.read_text(encoding="utf-8")
        assert partial_text != absent_text
        assert "BMAD absent" not in partial_text, partial_text

    def test_bmm_present_emits_nothing_at_all(self, install_sh_no_main, tmp_path):
        """AC-3: silence is the required behaviour — a reassuring line is a defect.

        Asserts the absence of *output*, not the absence of the word "warning".
        """
        project = _project(tmp_path, "full_bmad_project")
        _module_config(project)
        out_file = tmp_path / "out-present.txt"

        result = _report(install_sh_no_main, project, out_file)
        output = out_file.read_text(encoding="utf-8")

        assert result.returncode == 0, result.stderr
        assert output == "", f"expected silence when BMM is present, got: {output!r}"

    def test_bmm_present_emits_a_debug_line_only_at_debug_level(
        self, install_sh_no_main, tmp_path
    ):
        """The bmm-present arm exists and is reachable — asserted, not assumed.

        Without this, deleting the `bmm-present)` arm outright leaves the module
        green: an unmatched `case` also emits nothing on a normal run, so silence
        alone cannot tell a working arm from a missing one.
        """
        project = _project(tmp_path, "full_bmad_project")
        _module_config(project)
        out_file = tmp_path / "out-present-debug.txt"

        result = _report(install_sh_no_main, project, out_file, log_level="debug")
        output = out_file.read_text(encoding="utf-8")

        assert result.returncode == 0, result.stderr
        assert "BMM present" in output, output
        assert "WARNING" not in output, output

    def test_unrecognised_state_is_reported_rather_than_silent(
        self, install_sh_no_main, tmp_path
    ):
        """A state no arm matches must not be indistinguishable from success.

        The answer channel is stdout, a shared stream. Any future stray output
        inside the detector lands in `$state`, matches no arm — and because
        silence is this design's BMM-present signal, a detection failure would
        read as a clean run. The detector is replaced after sourcing so the
        default arm is exercised without weakening the real one.
        """
        out_file = tmp_path / "out-unrecognised.txt"
        bash_cmd = f"""
set -euo pipefail
source "{install_sh_no_main}"
detect_bmad_module_state() {{ echo "surprise-token"; return 0; }}
report_bmad_module_state "{tmp_path}" > "{out_file}" 2>&1
echo "REACHED_END=yes"
"""
        result = subprocess.run(
            ["bash", "-c", bash_cmd], capture_output=True, text=True, env=_env()
        )
        output = out_file.read_text(encoding="utf-8")

        assert result.returncode == 0, result.stderr
        assert "REACHED_END=yes" in result.stdout, result.stdout
        assert output.strip(), "unrecognised state produced silence"
        assert "surprise-token" in output, output

    def test_absence_messages_carry_no_version_and_no_upstream_source(
        self, install_sh_no_main, tmp_path
    ):
        """Scope boundary: the route out is Story 1.6's, and AD-1/AD-2 forbid it here."""
        project = _project(tmp_path, "partial_bmad_project", "_bmad/sample-module-one")
        out_file = tmp_path / "out.txt"

        _report(install_sh_no_main, project, out_file)
        output = out_file.read_text(encoding="utf-8")

        # Non-vacuity: an empty file satisfies every "not in" below, so assert
        # there is a message to inspect before inspecting it.
        assert "BMM" in output, output
        assert "http" not in output.lower(), output
        assert "github" not in output.lower(), output
        assert not re.search(r"\bv?\d+\.\d+", output), output


class TestIndeterminateEvidenceIsNotReportedAsAbsence:
    """The fourth state — evidence that exists and cannot be read.

    Round 1 shipped this case resolving silently to `bmm-absent`, and its suite
    declined to assert which state came out, citing AD-24 as an open question.
    The question was escalated and ruled on: report it, never abort. These tests
    assert the state, which is the half that was missing.
    """

    def test_unreadable_bmad_root_resolves_indeterminate(
        self, install_sh_no_main, unreadable_bmad_root
    ):
        """`[[ -d ]]` succeeds on a mode-000 directory; everything beneath fails."""
        result = _detect(install_sh_no_main, unreadable_bmad_root)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMAD_INDETERMINATE

    def test_unreadable_module_directory_resolves_indeterminate(
        self, install_sh_no_main, unreadable_module_dir
    ):
        """One level deeper: the root answers, the Module cannot be looked into."""
        result = _detect(install_sh_no_main, unreadable_module_dir)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMAD_INDETERMINATE

    def test_unsearchable_project_path_is_not_reported_as_bmad_absent(
        self, install_sh_no_main, unsearchable_project_path
    ):
        """The instance a `-L` guard is blind to: `_bmad` is a real directory.

        `[[ -d "$project_path/_bmad" ]]` resolves every component of the project
        path too, and fails identically on EACCES and ENOENT. Reporting absent
        here is a confident wrong answer about a machine that HAS BMM.
        """
        result = _detect(install_sh_no_main, unsearchable_project_path)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMAD_INDETERMINATE

    def test_symlinked_root_with_unresolvable_target_is_not_reported_as_bmad_absent(
        self, install_sh_no_main, symlinked_root_with_unresolvable_target
    ):
        """The shared-install instance: the node is there and cannot be resolved.

        `_bmad` mode 000 and this tree put the operator in the identical
        situation — `cat _bmad/bmm/config.yaml` is Permission denied on both — so
        answering `bmad-indeterminate` for one and `bmad-absent` for the other is
        an inconsistency in the design's own rule, not a severity gradient.
        """
        result = _detect(install_sh_no_main, symlinked_root_with_unresolvable_target)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMAD_INDETERMINATE

    def test_dangling_root_symlink_is_not_reported_as_bmad_absent(
        self, install_sh_no_main, tmp_path
    ):
        """A `_bmad` symlink whose target is gone: `[[ ]]` cannot say WHY it is gone.

        This case is bit-identical to the adjudicated permission case — both are
        `-L` true, `-e` false — because `[[ ]]` exposes no errno and cannot tell
        ENOENT from EACCES from ELOOP. One of the three is ruled indeterminate,
        so all three take that answer. Pinned in this direction because nothing
        pinned it in either direction before.
        """
        project = _project(tmp_path, "dangling_root_project")
        (project / "_bmad").symlink_to(tmp_path / "no_such_target")

        result = _detect(install_sh_no_main, project)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMAD_INDETERMINATE

    def test_self_referential_root_symlink_is_not_reported_as_bmad_absent(
        self, install_sh_no_main, tmp_path
    ):
        """A `_bmad` symlink loop: ELOOP, which `[[ -d ]]` renders as "not there".

        Needs no permission fixture, so it measures the same conflation on a
        filesystem that does not enforce modes.
        """
        project = _project(tmp_path, "symlink_loop_project")
        (project / "_bmad").symlink_to(project / "_bmad")

        result = _detect(install_sh_no_main, project)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMAD_INDETERMINATE

    def test_symlinked_module_with_unresolvable_target_is_not_reported_as_bmm_absent(
        self, install_sh_no_main, symlinked_module_with_unresolvable_target
    ):
        """The Module-level twin of the root's shared-install instance.

        `_bmad/bmm` mode 000 (one level down from the root's adjudicated case) and
        this tree put the operator in the identical situation — the Module's
        `config.yaml` is Permission denied on both — so the module guard must
        answer the same way the root guard already does for its own shared-install
        shape.
        """
        result = _detect(install_sh_no_main, symlinked_module_with_unresolvable_target)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMAD_INDETERMINATE

    def test_dangling_module_symlink_is_not_reported_as_bmm_absent(
        self, install_sh_no_main, tmp_path
    ):
        """A `_bmad/bmm` symlink whose target is gone: unresolved, not absent.

        Previously pinned as `bmm-absent` — an accident of what the code happened
        to do before the module guard gained the root's `-L`/`! -e` limb, not a
        decision about what it should do. Bit-identical to the root's dangling
        case (`[[ ]]` exposes no errno, so ENOENT, ELOOP and EACCES cannot be told
        apart here either), and the root already answers indeterminate for it —
        an unresolved node is never certified absent, at any depth.
        """
        project = _project(tmp_path, "dangling_module_symlink_project", "_bmad")
        (project / "_bmad" / "bmm").symlink_to(tmp_path / "no_such_target")

        result = _detect(install_sh_no_main, project)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMAD_INDETERMINATE

    def test_symlinked_module_config_with_unresolvable_target_is_not_reported_as_bmm_absent(
        self, install_sh_no_main, symlinked_module_config_with_unresolvable_target
    ):
        """One node further than the Module directory: `config.yaml` itself is the link.

        The same shared-install layout, applied to the per-file config link
        instead of the whole Module directory. The Module's `config.yaml` is
        Permission denied, exactly as the Module-directory and root shared-install
        instances already are, so it must resolve the same way they do.
        """
        result = _detect(
            install_sh_no_main, symlinked_module_config_with_unresolvable_target
        )

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMAD_INDETERMINATE

    def test_dangling_module_config_symlink_is_not_reported_as_bmm_absent(
        self, install_sh_no_main, tmp_path
    ):
        """A `_bmad/bmm/config.yaml` symlink whose target is gone: unresolved, not absent.

        The per-file twin of `test_dangling_module_symlink_is_not_reported_as_bmm_absent`.
        Bit-identical to the Module-directory and root dangling cases (`[[ ]]`
        exposes no errno here either), so it takes the same answer.
        """
        project = _project(tmp_path, "dangling_module_config_project", "_bmad/bmm")
        (project / "_bmad" / "bmm" / "config.yaml").symlink_to(
            tmp_path / "no_such_target"
        )

        result = _detect(install_sh_no_main, project)

        assert result.returncode == 0, result.stderr
        assert _state_of(result) == STATE_BMAD_INDETERMINATE

    def test_missing_argument_resolves_indeterminate(
        self, install_sh_no_main, tmp_path
    ):
        """No project path is not a licence to answer about some other project.

        Defaulting a missing argument to `.` or `pwd` would produce a confident
        answer about a directory the caller never named. Unknown is the honest
        state, and it is also the `set -u` fix: `${1:-}` where a bare `$1` would
        abort the shell before any test ran.
        """
        bash_cmd = f"""
set -euo pipefail
source "{install_sh_no_main}"
rc=0
state=$(detect_bmad_module_state) || rc=$?
echo "STATE=$state"
echo "RC=$rc"
echo "REACHED_END=yes"
"""
        result = subprocess.run(
            ["bash", "-c", bash_cmd], capture_output=True, text=True, env=_env()
        )

        assert result.returncode == 0, result.stderr
        assert "REACHED_END=yes" in result.stdout, result.stdout
        assert "RC=0" in result.stdout, result.stdout
        assert _state_of(result) == STATE_BMAD_INDETERMINATE

    def test_reporter_does_not_assert_absence_for_unreadable_evidence(
        self, install_sh_no_main, unreadable_bmad_root, tmp_path
    ):
        """The message must say "unknown", never "absent" — that is its whole job."""
        out_file = tmp_path / "out-indeterminate.txt"

        result = _report(install_sh_no_main, unreadable_bmad_root, out_file)
        output = out_file.read_text(encoding="utf-8")

        assert result.returncode == 0, result.stderr
        assert output.strip(), "indeterminate evidence reported nothing"
        assert "undetermined" in output.lower(), output
        assert "BMM absent" not in output, output
        assert "BMAD absent" not in output, output

    def test_indeterminate_is_distinguishable_from_both_absent_states(
        self, install_sh_no_main, unreadable_bmad_root, tmp_path
    ):
        """Three reports, three texts. Collapsing any two re-creates the defect."""
        absent = _project(tmp_path, "absent_project")
        partial = _project(tmp_path, "partial_project", "_bmad/sample-module-one")
        outs = {}
        for name, project in (
            ("indeterminate", unreadable_bmad_root),
            ("bmad_absent", absent),
            ("bmm_absent", partial),
        ):
            out_file = tmp_path / f"out-{name}.txt"
            _report(install_sh_no_main, project, out_file)
            outs[name] = out_file.read_text(encoding="utf-8")

        assert len(set(outs.values())) == 3, outs


class TestNeverAbortsTheInstall:
    """AC-4 — the detection path cannot change the installer's exit status."""

    @pytest.mark.parametrize(
        "dirs,write_config",
        [
            ((), False),
            (("_bmad/sample-module-one",), False),
            ((), True),
        ],
        ids=["bmad-absent", "bmm-absent", "bmm-present"],
    )
    def test_detector_returns_zero_in_every_state(
        self, install_sh_no_main, tmp_path, dirs, write_config
    ):
        """AC-4: design A carries its guarantee in the return status. Assert it."""
        project = _project(tmp_path, "project", *dirs)
        if write_config:
            _module_config(project)

        result = _detect(install_sh_no_main, project)

        assert "RC=0" in result.stdout, result.stdout
        assert "REACHED_END=yes" in result.stdout, result.stdout
        assert result.returncode == 0, result.stderr

    def test_detector_returns_zero_when_evidence_is_unreadable(
        self, install_sh_no_main, unreadable_bmad_root
    ):
        """AC-4: an internal step returning non-zero must not escape under errexit.

        An unreadable BMAD root makes the Module test fail rather than answer.
        This asserts AC-4 only — the run survives. *Which* state is reported is
        asserted separately, in TestIndeterminateEvidenceIsNotReportedAsAbsence;
        round 1 declined to assert it anywhere, and that gap is what let a silent
        misclassification ship behind a green suite.
        """
        result = _detect(install_sh_no_main, unreadable_bmad_root)

        assert "RC=0" in result.stdout, result.stdout
        assert "REACHED_END=yes" in result.stdout, result.stdout
        assert result.returncode == 0, result.stderr

    def test_reporter_survives_unreadable_evidence(
        self, install_sh_no_main, unreadable_bmad_root, tmp_path
    ):
        """AC-4: the reporting half of the path is subject to the same rule."""
        out_file = tmp_path / "out-unreadable.txt"

        result = _report(install_sh_no_main, unreadable_bmad_root, out_file)

        assert "REACHED_END=yes" in result.stdout, result.stdout
        assert result.returncode == 0, result.stderr

    def test_detector_returns_zero_for_a_nonexistent_project_path(
        self, install_sh_no_main, tmp_path
    ):
        """AC-4: a path that is not there is still not an abort."""
        result = _detect(install_sh_no_main, tmp_path / "no_such_project")

        assert "RC=0" in result.stdout, result.stdout
        assert result.returncode == 0, result.stderr

    def test_reporter_survives_being_called_with_no_argument(self, install_sh_no_main):
        """AC-4: `set -u` makes a bare `$1` fatal, and `|| true` cannot rescue it.

        Measured: a function whose body reads a bare `$1` with no argument
        supplied aborts the shell with "unbound variable" even as the left operand
        of `||`, and the following line never runs. The one abort class the
        "every filesystem read is a guarded [[ ]] test" framing does not cover,
        because it fires before the first test executes. Latent at today's sole
        call site, which always passes $PROJECT_PATH — and Story 1.6 is the named
        future caller.
        """
        bash_cmd = f"""
set -euo pipefail
source "{install_sh_no_main}"
report_bmad_module_state || true
echo "REACHED_END=yes"
"""
        result = subprocess.run(
            ["bash", "-c", bash_cmd], capture_output=True, text=True, env=_env()
        )

        assert "REACHED_END=yes" in result.stdout, (
            f"the reporter aborted the shell with no argument.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert result.returncode == 0, result.stderr
        assert "unbound variable" not in result.stderr, result.stderr

    def test_reporter_does_not_mask_a_failing_detector(
        self, install_sh_no_main, tmp_path
    ):
        """AC-4: the reporter captures with a plain assignment, never `local`.

        The story forbids `local`/`declare` on this capture by name, because a
        declaration command reports ITS OWN exit status and the detector's
        non-zero return vanishes into it. Nothing asserted that until now: every
        other reporter test runs the real detector, which returns 0 on every path,
        and the one test that substitutes a detector stubs it with `return 0`. So
        rewriting the capture as `local state=$(...)` left the module green.

        The harness is a BARE call, and that is the whole discriminator. Measured
        against both forms of the line:

            shipped `state=$(...)`      bare call -> shell exits 3, end not reached
            mutated `local state=$(...)` bare call -> shell exits 0, end reached

        Under `|| rc=$?` BOTH forms report 0 — errexit is suspended for a whole
        function body invoked as the left operand of `||` — so a guarded harness
        here would be a test that cannot fail.
        """
        bash_cmd = f"""
set -euo pipefail
source "{install_sh_no_main}"
detect_bmad_module_state() {{ echo "bmm-absent"; return 3; }}
report_bmad_module_state "{tmp_path}" > /dev/null 2>&1
echo "REACHED_END=yes"
"""
        result = subprocess.run(
            ["bash", "-c", bash_cmd], capture_output=True, text=True, env=_env()
        )

        assert result.returncode == 3, (
            "a non-zero detector return was masked: the reporter's capture is not "
            f"a plain assignment.\nrc={result.returncode}\nstdout:\n{result.stdout}"
        )
        assert "REACHED_END=yes" not in result.stdout, result.stdout

    def test_call_site_in_main_is_not_a_bare_consumption(self):
        """AC-4 / Anti-pattern 7: a bare call under `set -e` aborts the install.

        Design A already returns 0 unconditionally, so this is the second of two
        independent guarantees rather than the only one.
        """
        lines = _INSTALL_SH.read_text(encoding="utf-8").splitlines()

        # Bound main()'s body, so "in main()" is checked and not merely asserted
        # by the test's own name. A file-wide grep stays green if the call is
        # moved into a helper nothing invokes.
        start = next(i for i, line in enumerate(lines) if line.startswith("main() {"))
        end = next(i for i in range(start + 1, len(lines)) if lines[i] == "}")

        def call_sites(block):
            found = []
            for line in block:
                # Strip a trailing comment first: a comment containing "||" would
                # otherwise satisfy the guard check on its own.
                code = line.split("#", 1)[0].strip()
                if (
                    "report_bmad_module_state" in code
                    and "report_bmad_module_state()" not in code
                ):
                    found.append(code)
            return found

        in_main = call_sites(lines[start:end])
        whole_file = call_sites(lines)

        assert in_main, "no call site for report_bmad_module_state inside main()"
        assert in_main == whole_file, (
            "a call site exists outside main(): "
            f"{[c for c in whole_file if c not in in_main]!r}"
        )

        guarded_tail = re.compile(r"\|\|\s*(true|:)\s*$")
        for code in in_main:
            assert code.startswith("if ") or guarded_tail.search(code), (
                f"bare call site under `set -euo pipefail`: {code!r}. "
                "Consume it in a condition."
            )
            # "|| " alone is not enough: these are the shapes that consume the
            # call in a condition and then abort the install anyway, which is
            # exactly what AC-4 forbids.
            assert not re.search(
                r"\|\|\s*(exit|return)\b", code
            ), f"call site consumes the call and then aborts: {code!r}"
            assert (
                "|| {" not in code
            ), f"call site guards into a compound that may abort: {code!r}"

    def test_install_sh_still_runs_under_errexit(self):
        """The premise AC-4 rests on — asserted, not assumed."""
        source = _INSTALL_SH.read_text(encoding="utf-8")

        assert "\nset -euo pipefail\n" in source


class TestDeclaredExemptions:
    """AD-20a — the fixture pair, both directions.

    One tree the detector must flag as `bmm-absent`, and one tree per declared
    exemption it must not flag.
    """

    def test_flags_the_defect_it_reports(self, install_sh_no_main, tmp_path):
        """The fixture that must fail on the defect: BMAD root, no Module."""
        project = _project(tmp_path, "defect_project", "_bmad/sample-module-one")

        assert _state_of(_detect(install_sh_no_main, project)) == STATE_BMM_ABSENT

    def test_exempt_sibling_output_tree_is_not_a_bmad_root(
        self, install_sh_no_main, tmp_path
    ):
        """`_bmad-output/` is a similarly-named output tree, not a BMAD root."""
        project = _project(tmp_path, "output_tree_project", EXEMPT_SIBLING_OUTPUT_TREE)

        state = _state_of(_detect(install_sh_no_main, project))

        assert (
            state == STATE_BMAD_ABSENT
        ), f"detector fired on declared exemption {EXEMPT_SIBLING_OUTPUT_TREE!r}"

    def test_exempt_nested_bmad_root_belongs_to_another_project(
        self, install_sh_no_main, tmp_path
    ):
        """Detection resolves beneath the project path it is given (N-8)."""
        project = _project(tmp_path, "nested_project", EXEMPT_NESTED_BMAD_ROOT)

        state = _state_of(_detect(install_sh_no_main, project))

        assert (
            state == STATE_BMAD_ABSENT
        ), f"detector fired on declared exemption {EXEMPT_NESTED_BMAD_ROOT!r}"

    def test_exempt_module_installed_is_never_reported_as_missing(
        self, install_sh_no_main, tmp_path
    ):
        """The positive direction: an installed Module is not the defect."""
        project = _project(tmp_path, "installed_project")
        _module_config(project)

        state = _state_of(_detect(install_sh_no_main, project))

        assert (
            state == STATE_BMM_PRESENT
        ), f"detector fired on declared exemption {EXEMPT_MODULE_INSTALLED!r}"


class TestDetectionIsNotPersisted:
    """AD-26 — installing the dependency later must not require a reinstall."""

    def test_detector_writes_nothing_into_the_project(
        self, install_sh_no_main, tmp_path
    ):
        """Nothing about the degraded state may be cached into a durable artifact."""

        def fingerprint(root: Path):
            """Names *and* contents — a rewrite in place changes no path name."""
            out = {}
            for path in sorted(root.rglob("*")):
                key = str(path.relative_to(root))
                out[key] = (
                    hashlib.sha256(path.read_bytes()).hexdigest()
                    if path.is_file()
                    else "<dir>"
                )
            return out

        project = _project(tmp_path, "no_bmad_project", "docs")
        (project / "docs" / "existing.txt").write_text("unchanged\n", encoding="utf-8")
        before = fingerprint(project)

        result = _detect(install_sh_no_main, project)
        out_file = tmp_path / "out.txt"
        _report(install_sh_no_main, project, out_file)

        # Non-vacuity: a detector that never ran also writes nothing. Assert it ran.
        assert _state_of(result) == STATE_BMAD_ABSENT
        assert out_file.read_text(encoding="utf-8").strip()

        after = fingerprint(project)
        assert before == after


# ---------------------------------------------------------------------------
# Operator-text consistency — the surface no behavioural test can reach.
# ---------------------------------------------------------------------------
#
# Every test above runs the detector, and not one of them can fail while the CODE
# is right and the TEXT describing it is wrong. That is the defect this feature
# shipped with: the reporter's cause list and INSTALL.md's state table each
# asserted a set of causes the detector does not produce, and every existing
# assertion on the message — "undetermined" is present, "absent" is not, the three
# texts differ — was satisfied identically by the false string and by the corrected
# one. A guard that cannot tell those two apart is not a guard.
#
# These checks read install.sh and INSTALL.md as TEXT. They source nothing, copy
# nothing and execute nothing, and that is the design rather than a restriction:
# the property under test is agreement between two documents, and running the
# script cannot observe a disagreement between them.
#
# The node set they check against is DERIVED FROM THE CODE, never listed here. A
# hand-written list of nodes is one more copy to drift; adding a guard to the
# detector must make these fail until the prose is updated, which only works if
# the guards themselves are the input.


def _install_sh_text() -> str:
    return _INSTALL_SH.read_text(encoding="utf-8")


def _shell_function_body(text: str, name: str) -> str:
    """Slice one shell function out of install.sh, opening line to closing brace.

    Every line inside these two functions is indented, so a `\\n}\\n` is the close
    and cannot match anything internal. Asserted non-empty: a slice that silently
    came back blank would make every check built on it vacuously true.
    """
    start = text.index(f"\n{name}() {{\n")
    end = text.index("\n}\n", start)
    body = text[start:end]
    assert body.strip(), f"empty body sliced for {name}()"
    return body


def _detection_section() -> str:
    """The `### BMAD Module Detection` section of INSTALL.md, heading to next heading."""
    text = _INSTALL_MD.read_text(encoding="utf-8")
    start = text.index("### BMAD Module Detection")
    rest = text[start + 1 :]
    following = re.search(r"\n#{2,3} ", rest)
    section = rest[: following.start()] if following else rest
    assert "| What you see |" in section, "state table not found in detection section"
    return section


def _table_row(section: str, headline: str) -> str:
    """The one table row whose FIRST cell — the message column — carries `headline`.

    Matched on the first cell, not the whole line: rows cross-reference each
    other's states in their descriptions ("is reported `BMM undetermined`, not
    absent"), so a whole-line match returns three rows for one headline.
    """
    rows = [
        line
        for line in section.splitlines()
        if line.startswith("|") and headline in line.split("|")[1]
    ]
    assert len(rows) == 1, f"expected one row for {headline!r}, found {len(rows)}"
    return rows[0]


def _reporter_messages() -> list[str]:
    """Every operator-facing string `report_bmad_module_state` can emit."""
    body = _shell_function_body(_install_sh_text(), "report_bmad_module_state")
    found = re.findall(r'\blog_(?:warning|debug) "([^"]+)"', body)
    assert len(found) >= 4, f"message extraction found only {found!r}"
    return found


def _headline(message: str) -> str:
    """The leading phrase of a message, which is what the INSTALL.md table quotes."""
    return re.split(r"[—:.]", message, maxsplit=1)[0].strip()


def _indeterminate_guard_conditions() -> list[str]:
    """Each `[[ ]]` condition in the detector that resolves to the fourth state."""
    body = _shell_function_body(_install_sh_text(), "detect_bmad_module_state")
    lines = body.splitlines()
    conditions = []
    for index, line in enumerate(lines):
        if f'echo "{STATE_BMAD_INDETERMINATE}"' not in line:
            continue
        for candidate in reversed(lines[:index]):
            stripped = candidate.strip()
            if stripped.startswith("if [["):
                conditions.append(stripped)
                break
        else:
            raise AssertionError(f"no guard found above {line!r}")
    assert len(conditions) >= 4, f"guard extraction found only {conditions!r}"
    return conditions


# Path expression in a guard -> the token the prose describing it must use. The
# closing quote is part of each key, so `"$bmad_root"` cannot match inside
# `"$bmad_root/bmm"` and the three depths stay distinct.
_NODE_PROSE = {
    '"$bmad_root/bmm/config.yaml"': "_bmad/bmm/config.yaml",
    '"$bmad_root/bmm"': "_bmad/bmm",
    '"$bmad_root"': "_bmad",
    '"$project_path"': "project path",
}


def _indeterminate_nodes() -> set:
    """Prose tokens for every filesystem node at which the detector answers unknown."""
    nodes = {
        prose
        for condition in _indeterminate_guard_conditions()
        for expression, prose in _NODE_PROSE.items()
        if expression in condition
    }
    assert len(nodes) >= 3, f"node extraction found only {nodes!r}"
    return nodes


def _fourth_state_comment() -> str:
    """The `WHAT THE FOURTH STATE COVERS` paragraph of the detector's header."""
    text = _install_sh_text()
    start = text.index("# WHAT THE FOURTH STATE COVERS")
    return text[start : text.index("\n#\n", start)]


class TestOperatorTextMatchesTheDetector:
    """Cause-set claims in install.sh and INSTALL.md, against what the code produces.

    The failing mechanism these exist to stop: text that turns one predicate into
    an enumeration of named causes, each with its own remedy. `[[ -L x && ! -e x ]]`
    is a single bit; prose that expands it into "cause A or cause B, do X for A and
    Y for B" is wrong before anyone checks which causes it named, because the
    detector never identified which one it saw.
    """

    def test_every_reporter_message_has_a_row_in_the_install_md_table(self):
        """A message an operator can see and cannot look up is undocumented.

        The table is headed "What you see", so it is an enumeration, and an
        enumeration missing an arm is the omission form of the defect. This is
        derived from the `case` arms rather than counted, so a future arm added
        without a row fails here.
        """
        section = _detection_section()
        messages = _reporter_messages()
        missing = sorted(
            {_headline(m) for m in messages if _headline(m) not in section}
        )
        assert not missing, (
            f"reporter can emit {len(messages)} messages; these have no row in "
            f"INSTALL.md's state table: {missing}"
        )

    def test_bmad_absent_row_carves_out_an_unresolvable_root_symlink(self):
        """ "Not a directory" is true of a dangling `_bmad`, which is not absent.

        A `_bmad` symlink that fails to resolve answers the fourth state, not
        `bmad-absent`, while one that resolves to a regular file, FIFO, socket or
        device does answer absent. The row must carry the carve-out its neighbour
        already carries, or it over-claims on exactly the dangling case.
        """
        row = _table_row(_detection_section(), "BMAD absent")
        assert "symlink" in row, f"row names no symlink behaviour: {row}"
        assert "undetermined" in row, f"row lacks the fourth-state carve-out: {row}"

    def test_bmm_absent_row_names_every_discriminator_failure(self):
        """`-f && -s` is two halves, and both produce this state.

        `-f` is the node-type half and `-s` the emptiness half — an empty Module
        directory, a zero-byte config and a `config.yaml` that is not a regular
        file all resolve `bmm-absent`. The detector's own header says so; the row
        must not be the lossy copy.
        """
        detector = _shell_function_body(_install_sh_text(), "detect_bmad_module_state")
        assert '-f "$bmad_root/bmm/config.yaml"' in detector, "node-type half gone"
        assert '-s "$bmad_root/bmm/config.yaml"' in detector, "emptiness half gone"

        row = _table_row(_detection_section(), "BMAD present / BMM absent")
        for phrase in ("empty", "zero-byte", "not a regular file"):
            assert phrase in row, f"row does not name {phrase!r}: {row}"

    def test_fourth_state_comment_enumerates_every_indeterminate_node(self):
        """The header bills this paragraph narrow-but-complete, so it must be.

        A narrow claim that is also incomplete reads as exhaustive while it is
        not, which is worse than the general claim it replaced.
        """
        comment = _fourth_state_comment()
        missing = sorted(node for node in _indeterminate_nodes() if node not in comment)
        assert not missing, f"nodes the code guards and the comment omits: {missing}"

        if any('-z "$project_path"' in c for c in _indeterminate_guard_conditions()):
            assert "empty or missing" in comment.lower(), (
                "the detector answers the fourth state for an empty or missing "
                "project-path argument and the comment does not say so"
            )

    def test_indeterminate_operator_text_names_every_filesystem_node(self):
        """Operator-facing text covers the nodes an operator can actually reach.

        Scoped to filesystem nodes deliberately. The empty-argument condition is
        real in the function and unreachable through the installer, which
        normalises its project path before calling — so it belongs in the
        developer-facing comment above and not in operator guidance.

        OWED TO `W-1`'s ACCEPTANCE, recorded here because this is where it gets
        caught. The operator text no longer names the project path as a cause of
        the permissions kind: an unenterable project path is replaced by the
        installer's own working directory before the detector runs, so it cannot
        produce this state and naming it sends the operator to check a permission
        that emitted no message. When `W-1` fixes that normalisation the cause
        becomes reachable and **the permissions branch must name the project path
        again on both surfaces.** Nothing else is wired to notice: this test
        checks that every node the detector guards is named, and the project path
        stays named by the re-aimed sentence ("the one you meant") whether or not
        the permissions branch carries it — so this assertion passes either way
        and the restoration has to be carried by `W-1`, not discovered here.
        """
        nodes = _indeterminate_nodes()
        message = next(
            m for m in _reporter_messages() if m.startswith("BMM undetermined")
        )
        row = _table_row(_detection_section(), "BMM undetermined")

        for surface, text in (("operator message", message), ("INSTALL.md row", row)):
            missing = sorted(node for node in nodes if node not in text)
            assert not missing, f"{surface} omits nodes the detector guards: {missing}"

    def test_permission_caused_fourth_state_fixtures_are_pinned_by_name(self):
        """The three trees where a permission denial arrives through a symlink node.

        These are the evidence that the fourth state's causes do NOT partition
        into "a permissions problem" and "an unresolvable symlink": each is both
        at once — `-L` true, `-e` false, bit-identical to a dangling link, with
        BMM genuinely installed on the other end and a `chmod` on the target's
        parent as the actual remedy.

        Named rather than counted, because a cause-list assertion exercising only
        dangling links would pass while re-admitting the claim that these refute.
        They erode silently — a fixture deleted, or kept but no longer consumed —
        and this fails when they do.
        """
        source = Path(__file__).read_text(encoding="utf-8")
        fixtures = (
            "symlinked_root_with_unresolvable_target",
            "symlinked_module_with_unresolvable_target",
            "symlinked_module_config_with_unresolvable_target",
        )
        for name in fixtures:
            marker = f"def {name}(tmp_path):"
            assert marker in source, f"missing fixture {name}"

            start = source.index(marker)
            following = source.find("\n@pytest.fixture", start)
            body = source[start : following if following != -1 else len(source)]
            assert ".symlink_to(" in body, f"{name} builds no symlink"
            assert ".chmod(0o000)" in body, f"{name} builds no permission denial"

            assert re.search(
                rf"def test_\w+\([^)]*\b{name}\b", source
            ), f"{name} is defined but no test consumes it"

    def test_indeterminate_text_does_not_partition_causes_it_cannot_tell_apart(self):
        """The fourth state's causes overlap, so no surface may present a menu.

        `[[ -L x && ! -e x ]]` is one bit. It is true for a link whose target is
        missing (ENOENT), for a loop (ELOOP), and for a link into a shared BMAD
        install whose target's parent is unsearchable (EACCES) — and in that last
        case BMM is installed on the other end and a `chmod` on that parent is the
        remedy. Three fixtures build exactly that tree, one per node:
        `symlinked_root_with_unresolvable_target`,
        `symlinked_module_with_unresolvable_target` and
        `symlinked_module_config_with_unresolvable_target`.

        Each banned phrase below is a claim the text used to make and the fixtures
        above refute. They are pinned as phrases, not paraphrased, because the
        regression this stops is the exact sentence returning — and every other
        assertion in this module passed while it was there.
        """
        message = next(
            m for m in _reporter_messages() if m.startswith("BMM undetermined")
        )
        row = _table_row(_detection_section(), "BMM undetermined")

        banned = (
            ("two distinct causes", "the causes overlap at every symlink node"),
            ("no permission to fix", "a chmod on the link target's parent is a fix"),
            ("so it resolves", "removing a link never makes it resolve"),
            (
                "permission to enter it",
                "an unenterable project path cannot reach this state through main()",
            ),
            (
                "project path is correct",
                "install.sh normalises the project path to pwd before the detector "
                "runs, so this cause produces no warning at all",
            ),
        )
        required = (
            ("target", "the link target's parent is where the permission fix lives"),
            ("outside this project", "that directory is not under the project path"),
        )

        for surface, text in (("operator message", message), ("INSTALL.md row", row)):
            lowered = text.lower()
            for phrase, why in banned:
                assert (
                    phrase not in lowered
                ), f"{surface} still claims {phrase!r}: {why}"
            for phrase, why in required:
                assert phrase in lowered, f"{surface} omits {phrase!r}: {why}"
