"""Cause-aware reading of the Parzival enablement record (Story 1.1, AD-32).

Covers the three transports the record travels by, and the two semantics that a
naive implementation gets wrong:

  * absent cause  -> "unknown", NEVER "opt-out". An existing docker/.env carrying a
    bare PARZIVAL_ENABLED and no cause key is the normal state on every pre-existing
    install (both .env.example merge loops append only *missing* keys, so nothing
    back-fills it). Defaulting that to "opt-out" tells every operator whose install
    *failed* that they chose it — the exact conflation this story removes.
  * empty vs absent -> three readers disagree, so the divergence is asserted rather
    than assumed. MemoryConfig sets env_ignore_empty=True (empty collapses to
    absent), update_parzival_settings.read_env_file treats "KEY=" as
    present-and-empty, and the shell greps see the raw line either way.
"""

import re
from pathlib import Path

import pytest

from memory.config import MemoryConfig
from memory.parzival_state import (
    CAUSE_FAILED,
    CAUSE_OPT_OUT,
    CAUSE_UNKNOWN,
    disabled_message,
    resolve_cause,
)

#: Assignments to a record field: ``.parzival_enabled<something> =`` but not ``==``.
_RECORD_FIELD_ASSIGNMENT = re.compile(r"\.(parzival_enabled\w*)\s*=(?!=)")

#: The ONLY file whose ``INTENTIONAL-TYPO`` markers are honoured. Scoping the
#: exemption to this module is what stops it being self-service: previously any test
#: anywhere under tests/ could switch the guard off for its own line just by naming
#: the marker in a comment, which is an opt-out from a gate, granted by the code the
#: gate exists to police.
#:
#: KEYED ON FILE IDENTITY, NOT ON A BASENAME. ``path.name == "…cause.py"`` compares
#: the bare basename over an ``rglob`` walk, so ANY file anywhere under the scanned
#: root sharing this module's basename inherited the whole exemption. That is not
#: hypothetical here: duplicated test basenames are routine in this tree (measured —
#: ``test_config.py``, ``test_storage.py``, ``test_session_start.py``, … ), and a
#: same-named sibling under ``tests/integration/`` is an established pattern rather
#: than an invented one. Resolved-path identity is exempt-this-file-and-only-this-file.
_TYPO_EXEMPT_FILE = Path(__file__).resolve()


def _scan_for_bad_record_fields(root: Path, valid_fields) -> list[str]:
    """Return ``path:lineno: name`` for each record-field assignment not on the config.

    Shared by the real detector and by its SO-15 positive control, so the control
    drives the SAME file iteration, encoding handling, exemption logic and matching
    that the gate uses. A control that re-implements what it controls is two
    implementations agreeing with each other, which is not a gate.
    """
    offenders = []
    for path in sorted(root.rglob("test_*.py")):
        # errors="replace" so a single non-UTF-8 file under tests/ degrades to
        # mojibake on its own lines instead of raising and taking the whole scan --
        # and therefore the gate -- offline.
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "INTENTIONAL-TYPO" in line and path.resolve() == _TYPO_EXEMPT_FILE:
                continue
            for name in _RECORD_FIELD_ASSIGNMENT.findall(line):
                if name not in valid_fields:
                    offenders.append(f"{path.relative_to(root)}:{lineno}: {name}")
    return offenders


#: The record's three keys. A real operator shell exports these (the installer
#: writes them into settings.json, which Claude Code loads into the environment),
#: and process env outranks the env_file in pydantic-settings — so without this
#: the dev's own PARZIVAL_ENABLED=true silently overrides every fixture below.
_RECORD_KEYS = (
    "PARZIVAL_ENABLED",
    "PARZIVAL_ENABLED_CAUSE",
    "PARZIVAL_ENABLED_CONDITION",
)


@pytest.fixture(autouse=True)
def _isolate_record_env(monkeypatch):
    """Clear the record's keys from the ambient environment for every test here."""
    for key in _RECORD_KEYS:
        monkeypatch.delenv(key, raising=False)


def _config_from_env_text(tmp_path, text: str) -> MemoryConfig:
    """Build a MemoryConfig from a literal docker/.env body."""
    env_file = tmp_path / ".env"
    env_file.write_text(text, encoding="utf-8")
    return MemoryConfig(_env_file=str(env_file))


class TestTransportThreeCarriesTheCause:
    """TR-9: a docker/.env cause key must reach the MemoryConfig attribute.

    This is the test that fails if the config.py field declaration is skipped:
    model_config sets extra="ignore", so an undeclared PARZIVAL_ENABLED_CAUSE is
    silently discarded and every attribute-reading consumer is unreachable.
    """

    def test_cause_key_populates_the_attribute(self, tmp_path):
        config = _config_from_env_text(
            tmp_path,
            "PARZIVAL_ENABLED=false\n"
            "PARZIVAL_ENABLED_CAUSE=failed\n"
            "PARZIVAL_ENABLED_CONDITION=complete\n",
        )
        assert config.parzival_enabled is False
        assert config.parzival_enabled_cause == CAUSE_FAILED
        assert config.parzival_enabled_condition == "complete"

    def test_opt_out_cause_populates_the_attribute(self, tmp_path):
        config = _config_from_env_text(
            tmp_path, "PARZIVAL_ENABLED=false\nPARZIVAL_ENABLED_CAUSE=opt-out\n"
        )
        assert config.parzival_enabled_cause == CAUSE_OPT_OUT

    def test_partial_condition_is_representable(self, tmp_path):
        """Story 1.2 produces `partial`; 1.1 only has to make it representable."""
        config = _config_from_env_text(
            tmp_path,
            "PARZIVAL_ENABLED=false\nPARZIVAL_ENABLED_CONDITION=partial\n",
        )
        assert config.parzival_enabled_condition == "partial"


class TestAbsentCauseFailsClosedToUnknown:
    """TR-11: the pre-existing-install state must never be read as opt-out."""

    def test_absent_cause_resolves_to_unknown(self, tmp_path):
        config = _config_from_env_text(tmp_path, "PARZIVAL_ENABLED=false\n")
        assert resolve_cause(config) == CAUSE_UNKNOWN

    def test_absent_cause_is_never_opt_out(self, tmp_path):
        config = _config_from_env_text(tmp_path, "PARZIVAL_ENABLED=false\n")
        assert resolve_cause(config) != CAUSE_OPT_OUT

    def test_absent_condition_defaults_to_complete(self, tmp_path):
        config = _config_from_env_text(tmp_path, "PARZIVAL_ENABLED=false\n")
        assert config.parzival_enabled_condition == "complete"

    def test_unrecognised_cause_token_fails_closed(self, tmp_path):
        """A cause this build does not know is 'unknown', not a claim about intent."""
        config = _config_from_env_text(
            tmp_path, "PARZIVAL_ENABLED=false\nPARZIVAL_ENABLED_CAUSE=banana\n"
        )
        assert resolve_cause(config) == CAUSE_UNKNOWN


class TestEmptyVersusAbsentDivergence:
    """TR-10: empty is the canonical 'no cause', and readers disagree on it."""

    def test_empty_cause_collapses_to_absent_for_memoryconfig(self, tmp_path):
        """env_ignore_empty=True means the empty write does NOT arrive as ""."""
        config = _config_from_env_text(
            tmp_path, "PARZIVAL_ENABLED=true\nPARZIVAL_ENABLED_CAUSE=\n"
        )
        assert config.parzival_enabled_cause == CAUSE_UNKNOWN
        assert config.parzival_enabled is True

    def test_read_env_file_sees_empty_as_present_and_empty(self, tmp_path):
        """The settings.json transport reader disagrees with MemoryConfig here."""
        from update_parzival_settings import read_env_file

        env_file = tmp_path / ".env"
        env_file.write_text(
            "PARZIVAL_ENABLED=true\nPARZIVAL_ENABLED_CAUSE=\n", encoding="utf-8"
        )
        env = read_env_file(str(env_file))
        assert "PARZIVAL_ENABLED_CAUSE" in env, "present"
        assert env["PARZIVAL_ENABLED_CAUSE"] == "", "and empty"


class TestOperatorFacingWording:
    """The cause -> semantics mapping, stated once and rendered per convention."""

    def test_failed_never_advises_a_plain_reinstall(self):
        """The package is absent; re-running install.sh the way opt-out's
        remedy does cannot work — that is not this arm's remedy.

        H-2 (round 2): was pinned to the retired "PARZIVAL_ENABLED=true" flag
        token, which no longer appears anywhere in `_MESSAGES` (H-3 removed
        it from opt-out's remedy too) — so that assertion could no longer fail
        against the leak it was written to catch. Retargeted to "install.sh",
        the string opt-out's remedy now uniquely carries.
        """
        msg = disabled_message(CAUSE_FAILED)
        assert "install.sh" not in msg, msg

    def test_failed_names_the_failure(self):
        assert "could not be installed" in disabled_message(CAUSE_FAILED).lower()

    def test_opt_out_tells_the_operator_how_to_enable(self):
        msg = disabled_message(CAUSE_OPT_OUT)
        assert "install.sh" in msg, msg

    def test_unknown_makes_no_claim_about_which_cause(self):
        msg = disabled_message(CAUSE_UNKNOWN).lower()
        assert "declined" not in msg, msg
        assert "could not be installed" not in msg, msg

    @pytest.mark.parametrize("cause", [CAUSE_OPT_OUT, CAUSE_FAILED, CAUSE_UNKNOWN])
    def test_every_cause_renders_in_both_conventions(self, cause):
        """Plain CLI print and markdown are two renderings of ONE mapping."""
        plain = disabled_message(cause)
        markdown = disabled_message(cause, markdown=True)
        assert plain and markdown
        assert "`" not in plain, "plain rendering carries no markup"
        assert "`" in markdown, "markdown rendering backticks its keys"

    def test_the_three_causes_render_differently(self):
        """A fixture pair that cannot distinguish causes has not tested AC-3."""
        rendered = {
            disabled_message(c) for c in (CAUSE_OPT_OUT, CAUSE_FAILED, CAUSE_UNKNOWN)
        }
        assert len(rendered) == 3, rendered

    def test_opt_out_renderings_are_semantically_equivalent(self):
        """TD-1048: the both-conventions guard only checks backtick presence and
        cannot see a plain/markdown divergence — assert equivalence ourselves.
        """
        plain = disabled_message(CAUSE_OPT_OUT)
        markdown = disabled_message(CAUSE_OPT_OUT, markdown=True).replace("`", "")
        assert plain == markdown, (plain, markdown)


class TestTheFieldDefaultItself:
    """Pin `config.py`'s default="unknown" directly, not only end-to-end.

    With the migration correctly seeding no cause, rule 4's "absent => unknown" is
    carried by exactly two things: this one-line field default, and
    `normalize_cause`. Every other assertion in this suite reaches the default
    through a constructed MemoryConfig, so a change from "unknown" to "" or to
    "opt-out" would be caught only indirectly -- and changing it to "opt-out" is
    the specific mistake rule 4 exists to prevent. A single unguarded line holding
    up the whole read-side contract gets its own assertion.
    """

    def test_declared_default_is_unknown(self):
        field = MemoryConfig.model_fields["parzival_enabled_cause"]
        assert field.default == "unknown", (
            f"parzival_enabled_cause default is {field.default!r}. It must be "
            "'unknown': absent cause must never read as 'opt-out', which would "
            "tell an operator whose install failed that they chose it."
        )

    def test_declared_condition_default_is_complete(self):
        field = MemoryConfig.model_fields["parzival_enabled_condition"]
        assert field.default == "complete"

    def test_default_is_not_a_known_written_cause(self):
        """`unknown` is a read-side sentinel and must never be a writable token."""
        from memory.parzival_state import KNOWN_CAUSES

        assert MemoryConfig.model_fields["parzival_enabled_cause"].default not in (
            KNOWN_CAUSES
        )


class TestResolveCauseFailsClosedOnBadInput:
    """`resolve_cause` must not silently absorb a config that cannot answer.

    The old implementation used `getattr(config, "parzival_enabled_cause", "")`,
    which swallowed an undeclared field -- and with `extra="ignore"` on
    MemoryConfig, an undeclared field means the key from docker/.env is being
    silently discarded and every consumer reads `unknown` forever. That is a build
    defect, not an unrecorded cause.
    """

    def test_missing_attribute_raises_rather_than_reading_unknown(self):
        class ConfigWithoutTheField:
            parzival_enabled = False

        with pytest.raises(AttributeError):
            resolve_cause(ConfigWithoutTheField())

    def test_a_spec_bound_mock_that_never_assigned_the_attribute_raises(self):
        """MEASURED, and it refutes the sharper half of the review finding.

        The finding predicted that a `MagicMock(spec=MemoryConfig)` which never
        *assigns* `parzival_enabled_cause` would auto-create a MagicMock for it,
        `.strip().lower()` would return a MagicMock, `in KNOWN_CAUSES` would be
        False, and the result would be a silent `unknown`.

        That does not happen on this codebase, for a reason specific to pydantic v2:
        `spec=` builds its allowed-name set from `dir(MemoryConfig)`, and pydantic v2
        model fields are NOT class attributes -- they live in `model_fields`. So the
        spec-bound mock rejects the name outright and raises AttributeError. The
        mitigation is real but it is `spec=` doing the work, not the normaliser.

        Recorded as a passing assertion rather than deleted, because the protection
        is incidental to pydantic's internals: if MemoryConfig ever stops being a
        pydantic v2 model, this test flips to the silent-unknown behaviour the
        finding described, and the TypeError branch below becomes the live guard.
        """
        from unittest.mock import MagicMock

        config = MagicMock(spec=MemoryConfig)
        config.parzival_enabled = False
        with pytest.raises(AttributeError):
            resolve_cause(config)

    def test_an_unspecced_mock_raises_rather_than_resolving_unknown(self):
        """The case that IS live: a bare MagicMock, which auto-creates anything.

        This is the A-6 failure mode with no `spec=` mitigation in front of it.
        Under the old silent coercion it resolved to `unknown`, so a cause branch
        took the wrong path and the test still passed. It now raises at the seam.
        """
        from unittest.mock import MagicMock

        config = MagicMock()
        config.parzival_enabled = False
        with pytest.raises(TypeError, match="must be a str"):
            resolve_cause(config)


class TestDisabledMessageNormalisesItsArgument:
    """A caller passing a raw value instead of resolve_cause output must not
    silently render the *unknown* message and lose the cause -- the failure is
    invisible because `unknown` is a legitimate rendering."""

    @pytest.mark.parametrize("raw", ["FAILED", " failed ", '"failed"', "failed\r"])
    def test_raw_failed_values_still_render_the_failed_message(self, raw):
        assert disabled_message(raw) == disabled_message("failed")

    def test_an_unrecognised_value_still_renders_unknown(self):
        assert disabled_message("bogus") == disabled_message("unknown")


class TestSpecBindingHasABoundaryAndTyposAreCaught:
    """TR-8's `spec=MemoryConfig` mitigation is narrower than it reads.

    ``MagicMock``'s ``spec=`` enforces the allowed-name set on **reads**
    (``__getattr__``), **not on writes** (``__setattr__``). That asymmetry is what
    refutes the claim that a spec-bound mock cannot have pydantic field names
    assigned -- and it is exactly what leaves this hole open:

        config.parzival_enabled_casue = "failed"   # typo, succeeds SILENTLY  # INTENTIONAL-TYPO

    The real attribute is never set. The test then either raises ``AttributeError``
    on the correctly-spelled read -- a confusing failure that points at the
    production code rather than at the typo -- or asserts against a name **nothing
    in production reads**, and passes while testing nothing.

    TR-8 catches the hazard it was written for (an auto-created attribute on an
    unassigned name) and does NOT catch this one. The boundary is asserted here
    rather than left as prose, and the field names the cause-branching tests assign
    are pinned against ``MemoryConfig.model_fields`` so a typo fails at the seam.
    """

    def test_spec_enforces_reads_but_not_writes(self):
        from unittest.mock import MagicMock

        from memory.config import MemoryConfig

        mock = MagicMock(spec=MemoryConfig)

        # Reads of an unassigned pydantic field name DO raise -- pydantic v2 fields
        # are not class attributes, so dir() does not expose them.
        with pytest.raises(AttributeError):
            _ = mock.parzival_enabled_cause

        # ...but a WRITE of an arbitrary name succeeds, typo and all. This is the
        # boundary: spec= is not a spell-checker for assignments.
        mock.parzival_enabled_casue = "failed"  # INTENTIONAL-TYPO
        assert mock.parzival_enabled_casue == "failed"

    def test_every_record_field_assigned_by_a_test_is_a_real_config_field(self):
        """Static guard: a typo'd record-field assignment anywhere in tests/ fails.

        Scans for assignments to ``.parzival_enabled*`` and requires each name to
        exist on MemoryConfig. This is the check that converts a silent typo into a
        loud failure without depending on any individual test noticing.
        """
        tests_root = Path(__file__).resolve().parent.parent
        offenders = _scan_for_bad_record_fields(tests_root, MemoryConfig.model_fields)
        assert not offenders, (
            "these tests assign a record field name that does not exist on "
            "MemoryConfig — spec= does not enforce names on writes, so the "
            "assignment succeeded silently and the test asserts nothing:\n"
            + "\n".join(offenders)
        )

    def test_the_static_guard_can_actually_fail(self, tmp_path):
        """SO-15 positive control: a detector never observed failing is not a gate.

        Drives the REAL scanner over a seeded tree. The previous version re-compiled
        its own copy of the pattern and matched it against a string literal, so it
        proved only that a regex it had just typed worked. If the real scanner's file
        iteration, encoding handling or exemption logic broke, this control still
        passed — a second implementation agreeing with itself.
        """
        (tmp_path / "test_seeded_offender.py").write_text(
            'config.parzival_enabled_casue = "failed"\n',  # INTENTIONAL-TYPO
            encoding="utf-8",
        )
        offenders = _scan_for_bad_record_fields(tmp_path, MemoryConfig.model_fields)
        assert offenders == ["test_seeded_offender.py:1: parzival_enabled_casue"], (
            "the real scanner did not flag a seeded bad field name — the gate "
            f"cannot be observed failing, so it is not a gate: {offenders}"
        )

    def test_the_static_guard_passes_a_real_field(self, tmp_path):
        """Negative half of the control: it flags the bad name, not every name."""
        (tmp_path / "test_seeded_valid.py").write_text(
            'config.parzival_enabled_cause = "failed"\n', encoding="utf-8"
        )
        assert _scan_for_bad_record_fields(tmp_path, MemoryConfig.model_fields) == []

    def test_the_typo_exemption_is_not_self_service(self, tmp_path):
        """A file other than this module cannot exempt itself by naming the marker.

        The exemption existed for the two deliberate demonstrations in this module.
        Keyed on the line alone it was an opt-out from the gate available to every
        file the gate polices — including the typo'd test it would need to catch.
        """
        (tmp_path / "test_self_exempting.py").write_text(
            'config.parzival_enabled_casue = "failed"  # INTENTIONAL-TYPO\n',
            encoding="utf-8",
        )
        offenders = _scan_for_bad_record_fields(tmp_path, MemoryConfig.model_fields)
        assert offenders, (
            "a test outside this module switched the guard off for its own line "
            "just by naming INTENTIONAL-TYPO — the exemption is self-service"
        )

    def test_a_same_basename_impostor_does_not_inherit_the_exemption(self, tmp_path):
        """The exemption must key on file IDENTITY, not on a bare basename.

        The sibling above seeds a DIFFERENTLY named file, so it never travels this
        route: it passes just as well when the exemption is keyed on ``path.name``.
        This one seeds a file with this module's EXACT basename in another
        directory — which is what ``path.name == "…cause.py"`` over an ``rglob``
        walk would have exempted wholesale. Duplicate test basenames across
        directories are routine in this tree, so the impostor is an established
        pattern rather than an invented one.
        """
        impostor_dir = tmp_path / "integration"
        impostor_dir.mkdir()
        impostor = impostor_dir / _TYPO_EXEMPT_FILE.name
        impostor.write_text(
            'config.parzival_enabled_casue = "failed"  # INTENTIONAL-TYPO\n',
            encoding="utf-8",
        )
        offenders = _scan_for_bad_record_fields(tmp_path, MemoryConfig.model_fields)
        assert offenders == [
            f"integration/{_TYPO_EXEMPT_FILE.name}:1: parzival_enabled_casue"
        ], (
            "a file that merely shares this module's basename inherited its "
            f"INTENTIONAL-TYPO exemption and switched the gate off: {offenders}"
        )

    def test_a_non_utf8_file_does_not_abort_the_scan(self, tmp_path):
        """One undecodable file must not take the whole gate offline.

        ``read_text(encoding="utf-8")`` without ``errors=`` raises on the first
        non-UTF-8 file under tests/ and aborts the scan — so a single stray byte
        anywhere disables the detector for every file after it in sort order.
        """
        (tmp_path / "test_aaa_undecodable.py").write_bytes(b'x = "\xff\xfe"\n')
        (tmp_path / "test_zzz_offender.py").write_text(
            'config.parzival_enabled_casue = "failed"\n',  # INTENTIONAL-TYPO
            encoding="utf-8",
        )
        offenders = _scan_for_bad_record_fields(tmp_path, MemoryConfig.model_fields)
        assert any("parzival_enabled_casue" in o for o in offenders), (
            "the scan did not survive an undecodable file and never reached the "
            f"offender that sorts after it: {offenders}"
        )
