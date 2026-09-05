"""The fail-closed cause rule has FOUR readers. This asserts they agree.

AD-32 requires consumers to branch on the *cause*. The rule that turns a raw
``docker/.env`` value into a cause is implemented four times, because shell cannot
import Python:

1. ``memory.parzival_state.normalize_cause``      (the SDK, and its two callers
   ``resolve_cause`` / ``resolve_cause_from_env``)
2. ``scripts/install.sh::normalize_parzival_cause`` (via ``read_parzival_cause``)
3. ``scripts/upgrade.sh``'s Step 3.6 branch
4. ``scripts/update_parzival_settings.py::read_env_file`` — the transport-2 writer.
   It strips surrounding quotes but **does not lowercase**, so ``Failed`` reaches
   ``settings.json`` as ``Failed``; downstream normalisation saves it today. It was
   omitted from the list while the count said "four", in a module whose entire value
   proposition is "no copy escapes the table" — so the count was load-bearing and
   wrong. Covered by ``TestReaderFourIsInTheTable`` below.

They had already drifted inside a single commit: the Python copy applied
``.strip().lower()`` and neither shell copy did, while ``cut -d= -f2-`` passes
quotes and a CRLF carriage return straight through. The observable consequence was
the installer and the SDK reporting different causes **for the same file** --
``PARZIVAL_ENABLED_CAUSE=Failed`` resolved to ``failed`` in Python and ``unknown``
in the installer's own success panel.

A module docstring claiming the rule "lives here so it has a single definition"
does not make that true, and no amount of care keeps four copies aligned. The only
structural guarantee available across a language boundary is this: **one input
table, asserted to resolve identically through every implementation.** Change one
copy and this fails.

The shell implementations are executed as shipped -- ``install.sh`` through the
established no-main harness, and ``upgrade.sh``'s inline block by extracting the
real lines from the real file. Nothing here re-types the normalisation, because a
re-typed copy would be a fifth implementation and would agree with itself forever.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).parent.parent
_SCRIPTS = _REPO / "scripts"
_INSTALL_SH = _SCRIPTS / "install.sh"
_UPGRADE_SH = _SCRIPTS / "upgrade.sh"

sys.path.insert(0, str(_REPO / "src"))

from memory.parzival_state import normalize_cause  # noqa: E402

# (raw value as it appears after `KEY=` in docker/.env, expected resolved cause)
#
# Every row is a value the record can actually acquire: the installer writes the
# first two; an operator hand-edit or a Windows editor produces the rest. `unknown`
# is the fail-closed answer -- a cause token is a claim about operator intent and an
# unrecognised token supports no claim.
CAUSE_TABLE = [
    ("failed", "failed"),
    ("opt-out", "opt-out"),
    ("Failed", "failed"),
    ("OPT-OUT", "opt-out"),
    ("FaIlEd", "failed"),
    ("  failed", "failed"),
    ("failed  ", "failed"),
    ('"failed"', "failed"),
    ("'opt-out'", "opt-out"),
    ('  "failed"  ', "failed"),
    ("failed\r", "failed"),
    ("opt-out\r", "opt-out"),
    ("", "unknown"),
    ("   ", "unknown"),
    ("bogus", "unknown"),
    ("fail", "unknown"),
    ("opt out", "unknown"),
    ("optout", "unknown"),
    ("enabled", "unknown"),
    ("unknown", "unknown"),
]

_IDS = [f"{raw!r}->{want}" for raw, want in CAUSE_TABLE]


@pytest.fixture(scope="module")
def install_sh_no_main(tmp_path_factory) -> Path:
    """The real install.sh minus its final `main "$@"`, so it can be sourced."""
    tmp_path = tmp_path_factory.mktemp("install_sh")
    lines = _INSTALL_SH.read_text(encoding="utf-8").splitlines(keepends=True)
    assert lines[-1].strip() == 'main "$@"', (
        f"Expected last line 'main \"$@\"', got: {lines[-1]!r}. "
        "If install.sh structure changed, update this fixture."
    )
    copy = tmp_path / "install.sh"
    copy.write_text("".join(lines[:-1]), encoding="utf-8")
    copy.chmod(0o755)
    shutil.copy(_SCRIPTS / "_env_split_helpers.sh", tmp_path / "_env_split_helpers.sh")
    return copy


@pytest.fixture(scope="module")
def upgrade_sh_normalizer() -> str:
    """Extract upgrade.sh's inline normalisation as a runnable function.

    The lines are lifted from the shipped file rather than re-typed, so editing
    upgrade.sh changes what this test executes. If the block is renamed or removed
    the extraction fails loudly rather than silently testing nothing.
    """
    lines = _UPGRADE_SH.read_text(encoding="utf-8").splitlines()
    hits = [
        (i, ln)
        for i, ln in enumerate(lines)
        if re.match(r"^\s*PARZIVAL_CAUSE=", ln) and "$(grep" not in ln
    ]
    assert len(hits) >= 6, (
        "Could not extract upgrade.sh's PARZIVAL_CAUSE normalisation "
        f"(found {len(hits)} lines). If upgrade.sh moved that block, update this "
        "extraction -- do NOT re-type the normalisation here, that would make this "
        "test a fifth implementation agreeing with itself."
    )
    # The extraction assumes ONE contiguous block. If a PARZIVAL_CAUSE= assignment
    # ever appears elsewhere in upgrade.sh, a plain findall would splice unrelated
    # lines into the middle of the normaliser and this test would quietly start
    # exercising something that exists nowhere in the shipped script. Fail loudly
    # instead: a test that silently changes what it tests is worse than no test.
    idx = [i for i, _ in hits]
    assert idx == list(range(idx[0], idx[0] + len(idx))), (
        "upgrade.sh's PARZIVAL_CAUSE lines are no longer contiguous "
        f"(found at {[i + 1 for i in idx]}). The extraction below would splice "
        "unrelated lines into the normaliser. Narrow the extraction to the Step 3.6 "
        "block before trusting this test again."
    )
    inner = "\n".join(ln.strip() for _, ln in hits)
    # NO `case` ARM IS EMITTED HERE. An earlier version appended a hand-written
    # `case "$PARZIVAL_CAUSE" in opt-out|failed) ... *) unknown`, which re-typed the
    # half of the rule that actually decides `unknown` -- so if upgrade.sh's real
    # `case` gained an arm, lost `opt-out`, or reordered such that `*)` shadowed a
    # token, this module still passed. That is precisely the "fifth implementation
    # agreeing with itself" the docstring forbids, inside the module that forbids it.
    #
    # Extraction cannot supply the real arms either: upgrade.sh's `case` emits
    # COLOURED OPERATOR MESSAGES, not cause tokens, so it is not a runnable
    # normaliser. So this fixture is scoped to what it genuinely extracts -- the
    # string mangling -- and the whitelist is applied by the ONE canonical
    # definition (memory.parzival_state.normalize_cause) in the assertions below.
    # upgrade.sh's real `case` arms are covered by
    # tests/test_parzival_cause_fixture_pairs.py::TestUpgradeShHandoffGatePair,
    # which extracts them via `text.index("    esac", start)` and asserts on messages.
    return (
        "upgrade_normalize() {\n"
        '    PARZIVAL_CAUSE="$1"\n'
        f"{inner}\n"
        '    printf "%s\\n" "$PARZIVAL_CAUSE"\n'
        "}\n"
    )


def _write_env(tmp_path: Path, raw: str) -> Path:
    """Write a docker/.env carrying exactly this raw cause value."""
    env_dir = tmp_path / "docker"
    env_dir.mkdir(parents=True, exist_ok=True)
    env_file = env_dir / ".env"
    # newline="" so a \r in the value survives verbatim rather than being
    # translated -- a CRLF .env is one of the cases under test.
    with open(env_file, "w", encoding="utf-8", newline="") as fh:
        fh.write("PARZIVAL_ENABLED=false\n")
        fh.write(f"PARZIVAL_ENABLED_CAUSE={raw}\n")
        fh.write("PARZIVAL_ENABLED_CONDITION=complete\n")
    return env_file


@pytest.mark.parametrize("raw,expected", CAUSE_TABLE, ids=_IDS)
def test_python_normalizer(raw, expected):
    assert normalize_cause(raw) == expected


@pytest.mark.parametrize("raw,expected", CAUSE_TABLE, ids=_IDS)
def test_install_sh_read_parzival_cause(raw, expected, install_sh_no_main, tmp_path):
    """install.sh reads the real docker/.env through its real function."""
    env_file = _write_env(tmp_path, raw)
    res = subprocess.run(
        [
            "bash",
            "-c",
            f'set -uo pipefail\nsource "{install_sh_no_main}"\n'
            f'read_parzival_cause "{env_file}"\n',
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert res.stdout.strip() == expected, (
        f"install.sh resolved {raw!r} to {res.stdout.strip()!r}, "
        f"Python resolves it to {expected!r} — the installer and the SDK now "
        "disagree about the same file."
    )


@pytest.mark.parametrize("raw,expected", CAUSE_TABLE, ids=_IDS)
def test_upgrade_sh_inline_normalizer(raw, expected, upgrade_sh_normalizer, tmp_path):
    """upgrade.sh's Step 3.6 block, extracted from the shipped file and run."""
    env_file = _write_env(tmp_path, raw)
    script = (
        "set -uo pipefail\n"
        + upgrade_sh_normalizer
        + f'RAW=$(grep "^PARZIVAL_ENABLED_CAUSE=" "{env_file}" | head -1 | cut -d= -f2- || true)\n'
        'upgrade_normalize "$RAW"\n'
    )
    res = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr
    # The fixture extracts upgrade.sh's MANGLING only (its real `case` emits coloured
    # operator messages, not tokens, so it cannot be run as a normaliser). The
    # whitelist step is therefore applied here by the single canonical definition
    # rather than re-typed into the fixture. Mangling-stage agreement between the two
    # shell twins is asserted directly in the cross-check below.
    mangled = res.stdout.strip()
    assert (
        normalize_cause(mangled) == expected
    ), f"upgrade.sh mangled {raw!r} to {mangled!r}, which resolves to {normalize_cause(mangled)!r}, expected {expected!r}"


def test_all_three_implementations_agree_on_every_row(
    install_sh_no_main, upgrade_sh_normalizer, tmp_path
):
    """The equivalence claim stated directly, as one assertion over the whole table.

    The parametrized tests above pin each implementation against the expected
    column. This one pins them against *each other*, so a table row updated to
    match a drifted implementation still fails.

    "Three" is accurate for what THIS function compares: the SDK, install.sh's
    read_parzival_cause, and upgrade.sh's inline block. The fourth reader --
    update_parzival_settings.py::read_env_file -- is not a normaliser and is covered
    by TestReaderFourIsInTheTable below, because it diverges by design (it strips
    quotes but does not lowercase) and would fail an identity comparison.
    """
    disagreements = []
    for raw, _expected in CAUSE_TABLE:
        env_file = _write_env(tmp_path, raw)
        py = normalize_cause(raw)
        inst = subprocess.run(
            [
                "bash",
                "-c",
                f'set -uo pipefail\nsource "{install_sh_no_main}"\n'
                f'read_parzival_cause "{env_file}"\n',
            ],
            capture_output=True,
            text=True,
        ).stdout.strip()
        upg = subprocess.run(
            [
                "bash",
                "-c",
                "set -uo pipefail\n"
                + upgrade_sh_normalizer
                + f'RAW=$(grep "^PARZIVAL_ENABLED_CAUSE=" "{env_file}" | head -1 | cut -d= -f2- || true)\n'
                'upgrade_normalize "$RAW"\n',
            ],
            capture_output=True,
            text=True,
        ).stdout.strip()
        # upg is the MANGLING stage only (see the fixture); apply the whitelist via
        # the one canonical definition to compare like with like.
        if not (py == inst == normalize_cause(upg)):
            disagreements.append(
                f"  {raw!r}: python={py!r} install.sh={inst!r} "
                f"upgrade.sh={normalize_cause(upg)!r} (mangled {upg!r})"
            )

        # The two SHELL twins must mangle byte-identically, before any whitelist.
        # This is the comparison the removed re-typed `case` was hiding: it made the
        # upgrade.sh path look whitelisted-and-correct while its mangling could drift
        # away from install.sh's without any test noticing.
        # `raw` goes through the ENVIRONMENT, never interpolated into the script
        # text. Interpolating it would let a row like `"failed"` (quotes included,
        # and the table has such rows) be re-quoted by bash before the normaliser
        # ever saw it -- the harness would then compare a value neither
        # implementation was given, and agree.
        inst_mangled = subprocess.run(
            [
                "bash",
                "-c",
                f'set -uo pipefail\nsource "{install_sh_no_main}"\n'
                'normalize_parzival_cause "$RAW_CAUSE"\n',
            ],
            capture_output=True,
            text=True,
            env={**os.environ, "RAW_CAUSE": raw},
        ).stdout
        if inst_mangled != upg:
            disagreements.append(
                f"  {raw!r}: MANGLING drift — install.sh={inst_mangled!r} "
                f"upgrade.sh={upg!r}"
            )
    assert (
        not disagreements
    ), "The fail-closed cause rule has drifted between implementations:\n" + "\n".join(
        disagreements
    )


class TestTransportOneRoundTrip:
    """TR-9: write the record through the installer, read it back through shell.

    Transport 1 is the raw ``docker/.env`` read (``install.sh`` and ``upgrade.sh``
    both grep the file directly). Every other test here starts from a hand-written
    .env, which proves the reader but not that what the *writer* produces is what
    the reader can consume. A round-trip is the only form that pins both ends, and
    it is the form that catches a writer emitting a value the reader normalises to
    something else.
    """

    @pytest.mark.parametrize("cause", ["failed", "opt-out"])
    def test_installer_written_record_reads_back_identically(
        self, cause, install_sh_no_main, tmp_path
    ):
        install_dir = tmp_path / "rt"
        (install_dir / "docker").mkdir(parents=True)
        res = subprocess.run(
            [
                "bash",
                "-c",
                "set -uo pipefail\n"
                f'export INSTALL_DIR="{install_dir}"\n'
                f'source "{install_sh_no_main}"\n'
                f'INSTALL_DIR="{install_dir}"\n'
                f'set_parzival_enablement "false" "{cause}"\n'
                "read_parzival_cause\n",
            ],
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, res.stdout + res.stderr
        assert res.stdout.strip() == cause, res.stdout + res.stderr
        # And the SDK reads the same file to the same answer.
        raw = None
        for line in (install_dir / "docker" / ".env").read_text().splitlines():
            if line.startswith("PARZIVAL_ENABLED_CAUSE="):
                raw = line.partition("=")[2]
        assert normalize_cause(raw) == cause, raw

    def test_the_enabled_write_round_trips_to_unknown_not_to_a_stale_cause(
        self, install_sh_no_main, tmp_path
    ):
        """The enabling path writes an EMPTY cause; both readers must say unknown."""
        install_dir = tmp_path / "rt_enabled"
        (install_dir / "docker").mkdir(parents=True)
        res = subprocess.run(
            [
                "bash",
                "-c",
                "set -uo pipefail\n"
                f'export INSTALL_DIR="{install_dir}"\n'
                f'source "{install_sh_no_main}"\n'
                f'INSTALL_DIR="{install_dir}"\n'
                'set_parzival_enablement "false" "failed"\n'
                'set_parzival_enablement "true" ""\n'
                "read_parzival_cause\n",
            ],
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, res.stdout + res.stderr
        assert res.stdout.strip() == "unknown", (
            "a stale cause survived an enabling run — every cause-aware consumer "
            f"now reports a deploy failure on a working install: {res.stdout!r}"
        )


class TestReaderThreeSeesEmptyAsPresentAndEmpty:
    """TR-10's third reader: `update_parzival_settings.read_env_file`.

    The three readers deliberately DISAGREE about empty-vs-absent and the story
    requires that divergence be asserted rather than assumed:

    * ``MemoryConfig`` sets ``env_ignore_empty=True`` — empty collapses to absent,
      so the field default (`unknown`) is what arrives.
    * ``read_env_file`` treats ``KEY=`` as present-and-empty and copies ``""``
      into settings.json.
    * the shell greps see the raw line either way.

    TR-10 names all three; only the first two were ever asserted, and the shell
    readers were never driven with an empty cause at all (they are, above).
    """

    def _read_env_file(self):
        import importlib.util

        script = _SCRIPTS / "update_parzival_settings.py"
        spec = importlib.util.spec_from_file_location("equiv_ups", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_empty_cause_is_present_and_empty_for_this_reader(self, tmp_path):
        env_file = _write_env(tmp_path, "")
        env = self._read_env_file().read_env_file(env_file)
        assert "PARZIVAL_ENABLED_CAUSE" in env, (
            "read_env_file must see KEY= as present — it is what carries the record "
            "onto transport 2, where the hooks read it"
        )
        assert env["PARZIVAL_ENABLED_CAUSE"] == ""

    def test_that_empty_still_resolves_to_unknown_downstream(self, tmp_path):
        env_file = _write_env(tmp_path, "")
        env = self._read_env_file().read_env_file(env_file)
        assert normalize_cause(env["PARZIVAL_ENABLED_CAUSE"]) == "unknown"

    def test_the_state_vars_carry_the_whole_record(self):
        module = self._read_env_file()
        assert set(module.PARZIVAL_STATE_VARS) == {
            "PARZIVAL_ENABLED",
            "PARZIVAL_ENABLED_CAUSE",
            "PARZIVAL_ENABLED_CONDITION",
        }, module.PARZIVAL_STATE_VARS


class TestReaderFourIsInTheTable:
    """Reader 4 — ``update_parzival_settings.py::read_env_file`` (transport 2).

    It strips surrounding quotes but does NOT lowercase, so it is not equivalent to
    the other three at its own stage. That is tolerable only because everything
    downstream normalises; this pins both halves of that claim so a future change
    cannot quietly remove the second one.
    """

    @staticmethod
    def _read_env_file():
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "equiv_updater", _SCRIPTS / "update_parzival_settings.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.read_env_file

    @pytest.mark.parametrize("raw,expected", CAUSE_TABLE, ids=_IDS)
    def test_reader_four_agrees_after_downstream_normalisation(
        self, raw, expected, tmp_path
    ):
        env_file = _write_env(tmp_path, raw)
        got = self._read_env_file()(env_file).get("PARZIVAL_ENABLED_CAUSE", "")
        assert normalize_cause(got) == expected, (
            f"reader 4 produced {got!r} for {raw!r}, which normalises to "
            f"{normalize_cause(got)!r}, not {expected!r}"
        )

    def test_reader_four_does_not_lowercase_and_that_is_the_known_divergence(
        self, tmp_path
    ):
        """The divergence stated as a measurement, not left as a footnote."""
        env_file = _write_env(tmp_path, "Failed")
        got = self._read_env_file()(env_file)["PARZIVAL_ENABLED_CAUSE"]
        assert got == "Failed", (
            "if reader 4 starts lowercasing, this module's fourth entry is stale — "
            f"got {got!r}"
        )
        assert normalize_cause(got) == "failed"


class TestFormsThePostCutTableCannotExpress:
    """CAUSE_TABLE feeds `normalize_cause(raw)` on the POST-`cut` string.

    So the python-dotenv stage — where two real divergences actually live — is never
    in the loop, and no row can express them. Both are asserted here directly, on the
    whole line rather than on the value:

    * ``export PARZIVAL_ENABLED_CAUSE=failed`` — python-dotenv resolves it to
      ``failed``; the shell readers return ``unknown`` (no ``^KEY=`` match), and
      ``read_env_file`` produces a key literally named
      ``"export PARZIVAL_ENABLED_CAUSE"``, i.e. the cause reads as ABSENT and the
      disabled branch deletes it from settings.json.
    * ``PARZIVAL_ENABLED_CAUSE=failed # note`` — python-dotenv strips the comment;
      ``cut -d= -f2-`` passes it straight through, so the shell readers see
      ``failed # note`` and fail closed to ``unknown``.

    These are recorded rather than repaired: the readers are pre-existing and the
    forms are hand-edits. What is NOT acceptable is a table that silently implies
    coverage it does not have.
    """

    @staticmethod
    def _write_line(tmp_path: Path, line: str) -> Path:
        env_dir = tmp_path / "docker"
        env_dir.mkdir(parents=True, exist_ok=True)
        env_file = env_dir / ".env"
        env_file.write_text(f"PARZIVAL_ENABLED=false\n{line}\n", encoding="utf-8")
        return env_file

    def _shell(self, env_file: Path, install_sh_no_main: Path) -> str:
        return subprocess.run(
            [
                "bash",
                "-c",
                f'set -uo pipefail\nsource "{install_sh_no_main}"\n'
                f'read_parzival_cause "{env_file}"\n',
            ],
            capture_output=True,
            text=True,
        ).stdout.strip()

    def test_export_prefixed_line_diverges_between_dotenv_and_shell(
        self, tmp_path, install_sh_no_main
    ):
        from dotenv import dotenv_values

        env_file = self._write_line(tmp_path, "export PARZIVAL_ENABLED_CAUSE=failed")
        assert (
            normalize_cause(dotenv_values(env_file).get("PARZIVAL_ENABLED_CAUSE"))
            == "failed"
        )
        assert self._shell(env_file, install_sh_no_main) == "unknown"

        keys = TestReaderFourIsInTheTable._read_env_file()(env_file)
        assert "PARZIVAL_ENABLED_CAUSE" not in keys, (
            "reader 4 must see the export form as a DIFFERENT key (i.e. the cause "
            f"absent) — that is the divergence being pinned: {keys}"
        )

    def test_inline_comment_diverges_between_dotenv_and_shell(
        self, tmp_path, install_sh_no_main
    ):
        from dotenv import dotenv_values

        env_file = self._write_line(tmp_path, "PARZIVAL_ENABLED_CAUSE=failed # note")
        assert (
            normalize_cause(dotenv_values(env_file).get("PARZIVAL_ENABLED_CAUSE"))
            == "failed"
        )
        assert self._shell(env_file, install_sh_no_main) == "unknown"
