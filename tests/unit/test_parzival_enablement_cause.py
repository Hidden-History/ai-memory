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

import pytest

from memory.config import MemoryConfig
from memory.parzival_state import (
    CAUSE_FAILED,
    CAUSE_OPT_OUT,
    CAUSE_UNKNOWN,
    disabled_message,
    resolve_cause,
)

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

    def test_failed_never_advises_setting_the_flag(self):
        """The package is absent; 'set PARZIVAL_ENABLED=true' cannot work."""
        msg = disabled_message(CAUSE_FAILED)
        assert "PARZIVAL_ENABLED=true" not in msg, msg

    def test_failed_names_the_failure(self):
        assert "could not be installed" in disabled_message(CAUSE_FAILED).lower()

    def test_opt_out_tells_the_operator_how_to_enable(self):
        msg = disabled_message(CAUSE_OPT_OUT)
        assert "PARZIVAL_ENABLED=true" in msg, msg

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
